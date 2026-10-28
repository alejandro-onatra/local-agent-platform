"""Local identity source, persistent-key preservation and applied-runtime failures."""
import contextlib
import copy
import io
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import yaml
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('identity_local',ROOT/'scripts/identity/local.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class LocalStateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)/'identity'
        for name,value in [('BASE',self.base),('ADMIN_UID',os.getuid()),('DATA_UIDS',{n:os.getuid() for n in P.DATA_UIDS}),('SECRET_UIDS',{n:os.getuid() for n in P.SECRET_UIDS})]:
            patch=mock.patch.object(P,name,value);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(P,'ancestors');patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(P.shutil,'disk_usage',return_value=types.SimpleNamespace(free=20*1024**3));patch.start();self.addCleanup(patch.stop)
        self.helper,self.lock,self.rendered,self.config=P.bundle()
    def test_setup_is_idempotent_and_never_rotates_existing_credentials(self):
        self.assertFalse(P.setup(self.lock,self.rendered)['existing_state_preserved'])
        before={p.name:p.read_bytes() for p in (self.base/'secrets').iterdir()}
        self.assertTrue(P.setup(self.lock,self.rendered)['existing_state_preserved'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.base/'secrets').iterdir()})
        self.assertEqual(self.base.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o400 for p in (self.base/'secrets').iterdir()))
        self.assertNotIn(next(iter(before.values())),(self.base/'manifest.json').read_bytes())
    def test_partial_state_is_not_repaired_or_overwritten(self):
        self.base.mkdir();marker=self.base/'KEEP';marker.write_text('preserve')
        with self.assertRaises((P.LocalError,FileNotFoundError)):P.setup(self.lock,self.rendered)
        self.assertEqual(marker.read_text(),'preserve');self.assertFalse((self.base/'manifest.json').exists())
    def test_low_disk_space_stops_before_writing_state(self):
        with mock.patch.object(P.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(P.LocalError,'less_than_10_gib_storage_available'):P.setup(self.lock,self.rendered)
        self.assertFalse(self.base.exists())
    def test_missing_key_does_not_generate_replacement(self):
        P.setup(self.lock,self.rendered);key=self.base/'secrets/authentik-secret';key.unlink()
        with self.assertRaisesRegex(P.LocalError,'incomplete_identity_state'):P.setup(self.lock,self.rendered)
        self.assertFalse(key.exists())
    def test_changed_compose_or_mismatched_password_copies_fail(self):
        P.setup(self.lock,self.rendered);compose=self.base/'compose.yaml';compose.write_text('altered')
        with self.assertRaisesRegex(P.LocalError,'identity_compose_drift'):P.check_state(self.lock,self.rendered)
        compose.write_text(self.rendered)
        path=self.base/'secrets/authentik-password';path.chmod(0o600);path.write_text('a'*64);path.chmod(0o400)
        with self.assertRaisesRegex(P.LocalError,'identity_password_copies_differ'):P.check_state(self.lock,self.rendered)
    def test_valid_format_secret_replacement_requires_explicit_recovery(self):
        P.setup(self.lock,self.rendered);key=self.base/'secrets/authentik-secret'
        key.chmod(0o600);key.write_text('a'*96);key.chmod(0o400)
        with self.assertRaisesRegex(P.LocalError,'identity_secret_integrity_drift'):P.setup(self.lock,self.rendered)
        self.assertEqual(key.read_text(),'a'*96)

    def test_manifest_boolean_version_and_duplicate_fields_fail(self):
        P.setup(self.lock,self.rendered);path=self.base/'manifest.json';data=json.loads(path.read_text());data['schema_version']=True;path.write_text(json.dumps(data))
        with self.assertRaises(P.LocalError):P.check_state(self.lock,self.rendered)
        path.write_text('{"purpose":"one","purpose":"two"}')
        with self.assertRaises(ValueError):P.check_state(self.lock,self.rendered)
    def test_linked_and_public_private_files_are_rejected(self):
        path=self.base/'value';self.base.mkdir();path.write_bytes(b'a'*64);path.chmod(0o400)
        self.assertEqual(P.read_file(path,os.getuid(),0o400,96),b'a'*64)
        alias=self.base/'alias';alias.hardlink_to(path)
        with self.assertRaises(P.LocalError):P.read_file(path,os.getuid(),0o400,96)
        alias.unlink();path.chmod(0o644)
        with self.assertRaises(P.LocalError):P.read_file(path,os.getuid(),0o400,96)
        path.unlink();path.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):P.read_file(path,os.getuid(),0o400,96)
    def test_fifo_private_file_is_rejected_without_blocking(self):
        self.base.mkdir();path=self.base/'fifo';os.mkfifo(path,0o400)
        context=multiprocessing.get_context('fork');receiver,sender=context.Pipe(duplex=False)
        def worker():
            try:P.read_file(path,os.getuid(),0o400,96);sender.send(False)
            except P.LocalError:sender.send(True)
        child=context.Process(target=worker);child.start();sender.close()
        try:self.assertTrue(receiver.poll(2));self.assertTrue(receiver.recv())
        finally:
            if child.is_alive():child.terminate()
            child.join(2);child.close();receiver.close()
    def test_environment_failure_stops_before_docker(self):
        engine=mock.Mock()
        with mock.patch.object(P,'check_state',side_effect=P.LocalError('missing_state')):
            with self.assertRaises(P.LocalError):P.operate('up',engine,self.lock,self.rendered,self.config)
        engine.run.assert_not_called()

class LocalRuntimeTests(unittest.TestCase):
    def setUp(self):
        _,self.lock,self.rendered,self.config=P.bundle();self.engine=mock.Mock();self.records={}
        for index,(name,service) in enumerate(self.config['services'].items(),1):
            cid=str(index)*64;networks={P.PROJECT+'_'+n:{} for n in service['networks']}
            self.records[cid]={'image':service['image'],'user':service['user'],
              'command':service.get('command',['postgres']),'entrypoint':['docker-entrypoint.sh'] if name=='database' else ['dumb-init','--','ak'],
              'labels':{'com.docker.compose.project':P.PROJECT,'com.docker.compose.service':name},
              'state':{'Running':True,'health':'healthy'},'apparmor':'docker-default','networks':networks,
              'mounts':[{'Type':'bind','Source':v['source'],'Destination':v['target'],'RW':not v.get('read_only',False)} for v in service['volumes']],
              'host':{'ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true','apparmor=docker-default'],
                'PidMode':'','IpcMode':'private','UTSMode':'','NetworkMode':next(iter(networks)),
                'Memory':{'768m':768*1024**2,'1g':1024**3,'2g':2*1024**3}[service['mem_limit']],
                'NanoCpus':service['cpus']*1_000_000_000,'PidsLimit':service['pids_limit'],
                'LogConfig':{'Type':'json-file','Config':{'max-file':'2','max-size':'2m'}},
                'Tmpfs':dict(item.split(':',1) for item in service['tmpfs']),
                'PortBindings':{'9000/tcp':[{'HostIp':'127.0.0.1','HostPort':'9000'}]} if name=='server' else {}}}
        def run(args,**kwargs):
            if args[0]=='ps':return 0,'\n'.join(self.records).encode()
            if args[0]=='inspect':return 0,json.dumps(self.records[args[-1]]).encode()
            if args[:2]==['network','inspect']:return 0,json.dumps({'driver':'bridge','internal':args[-1].endswith('_database')}).encode()
            raise AssertionError(args)
        self.engine.run.side_effect=run
    def test_expected_runtime_passes_but_no_household_acceptance_is_inferred(self):
        with mock.patch.object(P,'check_state'),mock.patch.object(P,'http_ready',return_value=True):
            result=P.operate('check',self.engine,self.lock,self.rendered,self.config)
        self.assertEqual(result['status'],'passed');self.assertEqual(result['blueprint_application'],'not_performed_by_this_task')
        self.assertEqual(result['browser_mfa_acceptance'],'pending')
    def test_wildcard_ipv6_and_extra_published_ports_are_rejected(self):
        record=self.records['2'*64];original=copy.deepcopy(record['host']['PortBindings'])
        for ip in ('0.0.0.0','::','127.0.0.2'):
            record['host']['PortBindings']['9000/tcp'][0]['HostIp']=ip
            with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config)
        record['host']['PortBindings']=original;record['host']['PortBindings']['9443/tcp']=[{'HostIp':'127.0.0.1','HostPort':'9443'}]
        with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config)
    def test_runtime_security_namespace_mount_image_and_command_drift_fail(self):
        original=copy.deepcopy(self.records['1'*64])
        changes=[lambda r:r.update(image='other:latest'),lambda r:r.update(user='0:0'),
                 lambda r:r.update(command=['sh']),lambda r:r['host'].update(ReadonlyRootfs=False),
                 lambda r:r['host'].update(PidMode='container:other'),lambda r:r['host'].update(IpcMode='host'),
                 lambda r:r['host'].update(CapAdd=['SYS_ADMIN']),lambda r:r['host'].update(Memory=0),
                 lambda r:r['mounts'][0].update(Source='/var/run/docker.sock'),
                 lambda r:r['mounts'].append({'Type':'volume'}),lambda r:r['networks'].update(foreign={})]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.records['1'*64]=copy.deepcopy(original);change(self.records['1'*64])
                with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config)
    def test_stopped_missing_or_unhealthy_services_never_pass_check(self):
        for running,health in ((False,'healthy'),(True,'unhealthy'),(True,'none')):
            self.records['1'*64]['state']={'Running':running,'health':health}
            with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config,require_all=True)
        self.records.clear()
        with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config,require_all=True)
    def test_foreign_project_and_worker_relabelling_are_rejected(self):
        self.records['1'*64]['labels']['com.docker.compose.project']='other'
        with self.assertRaises(P.LocalError):P.runtime(self.engine,self.config)
    def test_down_targets_only_this_project_and_preserves_files(self):
        original=self.engine.run.side_effect
        def run(args,**kwargs):
            if args[0]=='compose':return 0,b''
            return original(args,**kwargs)
        self.engine.run.side_effect=run
        with tempfile.TemporaryDirectory() as folder:
            keep=Path(folder)/'keep';keep.write_text('preserve')
            with mock.patch.object(P,'check_state'):
                result=P.operate('down',self.engine,self.lock,self.rendered,self.config)
            self.assertEqual(keep.read_text(),'preserve')
        self.assertTrue(result['persistent_state_preserved'])
        mutations=[call.args[0] for call in self.engine.run.call_args_list if call.args[0][0]=='compose']
        self.assertEqual(mutations,[['compose','--project-name',P.PROJECT,'--file',str(P.BASE/'compose.yaml'),'down','--timeout','15']])
        self.assertNotIn('--volumes',mutations[0])
    def test_up_rechecks_existing_restrictions_before_idempotent_start(self):
        original=self.engine.run.side_effect
        def run(args,**kwargs):
            if args[0] in ('compose','pull'):return 0,b''
            return original(args,**kwargs)
        self.engine.run.side_effect=run
        with mock.patch.object(P,'check_state'),mock.patch.object(P,'http_ready',return_value=True), \
             mock.patch.object(P.Path,'read_text',return_value='MemAvailable: 8388608 kB\n'):
            result=P.operate('up',self.engine,self.lock,self.rendered,self.config)
        self.assertEqual(result['ui_url'],'http://127.0.0.1:9000')
        calls=[call.args[0] for call in self.engine.run.call_args_list]
        self.assertTrue(any('up' in args for args in calls));self.assertFalse(any('down' in args for args in calls))
    def test_busy_loopback_port_prevents_pulls_or_service_start(self):
        engine=mock.Mock()
        with mock.patch.object(P,'check_state'),mock.patch.object(P,'runtime',return_value={}), \
             mock.patch.object(P.Path,'read_text',return_value='MemAvailable: 8388608 kB\n'),mock.patch.object(P.socket,'socket') as sock:
            sock.return_value.__enter__.return_value.bind.side_effect=OSError('busy')
            with self.assertRaisesRegex(P.LocalError,'identity_loopback_port_in_use'):P.operate('up',engine,self.lock,self.rendered,self.config)
        engine.run.assert_not_called()
    def test_public_database_bridge_is_rejected_at_runtime(self):
        original=self.engine.run.side_effect
        def run(args,**kwargs):
            if args[:2]==['network','inspect']:return 0,b'{"driver":"bridge","internal":false}'
            return original(args,**kwargs)
        self.engine.run.side_effect=run
        with self.assertRaisesRegex(P.LocalError,'identity_network_policy_drift'):P.runtime(self.engine,self.config)
    def test_nonroot_setup_never_writes_state_or_starts_services(self):
        with mock.patch.object(P.sys,'argv',['local.py','setup']),mock.patch.object(P.os,'geteuid',return_value=1000), \
             mock.patch.object(P,'setup') as setup,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(P.main(),1)
        setup.assert_not_called();self.assertIn('host_admin_required',output.getvalue())

    def test_failed_http_readiness_is_not_success(self):
        with mock.patch.object(P,'check_state'),mock.patch.object(P,'http_ready',return_value=False):
            with self.assertRaisesRegex(P.LocalError,'identity_http_not_ready'):P.operate('check',self.engine,self.lock,self.rendered,self.config)

if __name__=='__main__':unittest.main()
