"""Full restore rehearsal boundaries, lifecycle failures and browser evidence."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import subprocess
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
B=load('rehearsal_backup_test','scripts/identity/backup.py')
R=load('rehearsal_test','scripts/identity/rehearsal.py')
P=B.local_module()
TABLES='a'*32+'|42'

def native():
    return {'status':'passed','secret_loaded':True,'signing_roundtrip':True,'host_only_cookie':True,
            'active_users_present':True,'confirmed_totp_present':True,'totp_material_readable':True,
            'login_events':10,'totp_max_step':42}

def payload():
    return {'database.dump':b'PGDMPsynthetic','compose.yaml':b'untrusted archive config must not execute',
            'versions.yaml':b'pinned','manifest.json':b'{}','secrets/postgres-password':b'a'*64,
            'secrets/authentik-password':b'a'*64,'secrets/authentik-secret':b'b'*96,
            'data/icons/item':b'icon','certs/item':b'cert'}


class ConfigurationTests(unittest.TestCase):
    def test_registered_shell_plan_really_executes_without_sudo_or_age(self):
        result=subprocess.run(['bash',str(ROOT/'scripts/identity/backup.sh'),'rehearsal-plan'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['ui_url'],R.URL)

    def test_derived_compose_never_uses_live_state_or_wildcard_origin(self):
        lock,config,rendered=R.configuration(P)
        self.assertEqual(config['services']['server']['ports'],['127.0.0.2:19000:9000'])
        self.assertEqual(config['networks'],{'database':{'internal':True},'frontend':{'internal':True}})
        self.assertNotIn(str(P.BASE),rendered)
        for name,service in config['services'].items():
            self.assertEqual(service['logging'],{'driver':'none'})
            self.assertTrue(service['read_only']);self.assertEqual(service['cap_drop'],['ALL'])
            for mount in service['volumes']:
                self.assertTrue(mount['source'].startswith((str(R.STATE)+'/',str(R.CONTROL)+'/')))
                self.assertNotIn('docker.sock',mount['source'])
        self.assertEqual(lock['authentik']['version'],'2026.8.4')

    def test_modified_profile_including_boolean_schema_fails(self):
        helper=P.native();source=helper.source_module()
        for field,value in [('schema_version',True),('listen',{'address':'0.0.0.0','port':19000}),('reuse_live_state',True)]:
            changed=copy.deepcopy(R.PROFILE);changed[field]=value
            original=source.parse
            def parse(raw):
                text=raw.decode() if isinstance(raw,bytes) else raw
                if 'isolated_identity_restore_rehearsal' in text:return changed
                return original(raw)
            with mock.patch.object(source,'parse',side_effect=parse),mock.patch.object(helper,'source_module',return_value=source),mock.patch.object(P,'bundle',return_value=(helper,{},'',{})):
                with self.assertRaisesRegex(R.RehearsalError,'profile_drift'):R.configuration(P)

    def test_runtime_passes_explicit_loopback_and_internal_network_boundaries(self):
        local=mock.Mock();R.runtime(local,'engine','config',required=True)
        local.runtime.assert_called_once_with('engine','config',require_all=True,project=R.PROJECT,
            address='127.0.0.2',port=19000,internal_networks=('database','frontend'))

    def test_native_probe_rejects_secret_or_cookie_failure_and_unexpected_fields(self):
        engine=mock.Mock()
        for change in ({'secret_loaded':False},{'host_only_cookie':False},{'login_events':True},{'unexpected':'private'}):
            result={**native(),**change}
            engine.run.return_value=(0,b'IDENTITY_REHEARSAL_RESULT='+json.dumps(result).encode())
            with self.assertRaises(R.RehearsalError):R.native_probe(engine,'check')

    def test_applied_rehearsal_runtime_rejects_public_port_or_external_bridge(self):
        legacy=load('rehearsal_runtime_fixture','tests/security/test_identity_local.py')
        fixture=legacy.LocalRuntimeTests();fixture.setUp()
        _,config,_=R.configuration(P)
        records=fixture.records
        for record in records.values():
            name=record['labels']['com.docker.compose.service'];service=config['services'][name]
            networks={R.PROJECT+'_'+n:{} for n in service['networks']}
            record['labels']['com.docker.compose.project']=R.PROJECT;record['networks']=networks
            record['host']['NetworkMode']=next(iter(networks));record['host']['LogConfig']={'Type':'none','Config':{}}
            record['host']['PortBindings']={'9000/tcp':[{'HostIp':R.ADDRESS,'HostPort':str(R.PORT)}]} if name=='server' else {}
            record['mounts']=[{'Type':'bind','Source':v['source'],'Destination':v['target'],'RW':not v.get('read_only',False)} for v in service['volumes']]
        internal=True
        def run(args,**kwargs):
            if args[0]=='ps':return 0,'\n'.join(records).encode()
            if args[0]=='inspect':return 0,json.dumps(records[args[-1]]).encode()
            if args[:2]==['network','inspect']:return 0,json.dumps({'driver':'bridge','internal':internal}).encode()
            raise AssertionError(args)
        engine=mock.Mock();engine.run.side_effect=run
        self.assertEqual(set(R.runtime(P,engine,config,required=True)),{'database','server','worker'})
        records['2'*64]['host']['PortBindings']['9000/tcp'][0]['HostIp']='0.0.0.0'
        with self.assertRaises(P.LocalError):R.runtime(P,engine,config,required=True)
        records['2'*64]['host']['PortBindings']['9000/tcp'][0]['HostIp']=R.ADDRESS;internal=False
        with self.assertRaises(P.LocalError):R.runtime(P,engine,config,required=True)

    def test_native_probe_success_does_not_accept_raw_diagnostics(self):
        engine=mock.Mock();engine.run.return_value=(0,b'IDENTITY_REHEARSAL_RESULT='+json.dumps(native()).encode())
        self.assertEqual(R.native_probe(engine,'check')['status'],'passed')
        engine.run.return_value=(1,b'IDENTITY_REHEARSAL_RESULT='+json.dumps(native()).encode())
        with self.assertRaises(R.RehearsalError):R.native_probe(engine,'check')
        engine.run.return_value=(0,b'private traceback without fixed result')
        with self.assertRaises(R.RehearsalError):R.native_probe(engine,'check')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'rehearsal'
        for name,value in [('BASE',self.base),('STATE',self.base/'state'),('CONTROL',self.base/'control')]:
            patch=mock.patch.object(R,name,value);patch.start();self.addCleanup(patch.stop)
        def write(path,data,uid,mode):
            with path.open('xb') as handle:handle.write(data)
            path.chmod(mode)
        def directory(path,uid,mode=0o700):
            self.assertTrue(path.is_dir());self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode&0o777,mode)
        def read(path,uid,mode,limit):
            self.assertEqual(path.lstat().st_mode&0o777,mode)
            return B.safe_read(path,limit)
        self.local=types.SimpleNamespace(bundle=P.bundle,native=P.native,ancestors=mock.Mock(),
            directory=directory,write_file=write,read_file=read,runtime=mock.Mock(),http_ready=mock.Mock(return_value=True))
        self.engine=mock.Mock();self.mounted=False
        def run(args,**kwargs):
            if args[0]=='mount':self.mounted=True
            if args[0]=='umount':
                self.mounted=False
                # Model an unmounted RAM fs, without touching any real mount.
                import shutil
                for path in R.STATE.iterdir():
                    if path.is_dir():shutil.rmtree(path)
                    else:path.unlink()
            return 0,b''
        self.engine.run.side_effect=run
        def mount(engine):return {'fstype':'tmpfs'} if self.mounted else None
        for obj,name,value in [(R,'inspect_mount',mount),(B,'table_inventory',mock.Mock(return_value=TABLES)),
                               (B,'stream_command',mock.Mock()),(R,'native_probe',mock.Mock(return_value=native())),
                               (R.os,'chown',mock.Mock()),(R,'require_resources',mock.Mock())]:
            patch=mock.patch.object(obj,name,value);patch.start();self.addCleanup(patch.stop)
        self.lock,self.config,self.rendered=R.configuration(self.local)

    def start(self):return R.start(self.engine,B,self.local,self.lock,B.pack(payload(),self.lock,TABLES))

    def test_success_restores_secrets_files_and_keeps_browser_pending(self):
        result=self.start()
        self.assertEqual(result['browser_acceptance'],'pending_owner_confirmation')
        self.assertEqual((R.STATE/'data/icons/item').read_bytes(),b'icon')
        self.assertEqual((R.STATE/'secrets/authentik-secret').stat().st_mode&0o777,0o400)
        self.assertNotIn(b'untrusted archive config',(R.CONTROL/'compose.yaml').read_bytes())
        self.assertEqual(json.loads((R.CONTROL/'baseline.json').read_text()),{'login_events':10,'totp_max_step':42})
        self.assertFalse(result['browser_evidence']['new_login_event'])

    def test_existing_state_or_project_collision_never_overwritten(self):
        self.base.mkdir();marker=self.base/'KEEP';marker.write_text('preserve')
        with self.assertRaisesRegex(R.RehearsalError,'exists'):self.start()
        self.assertEqual(marker.read_text(),'preserve')
        marker.unlink();self.base.rmdir();self.engine.run.side_effect=None;self.engine.run.return_value=(0,b'foreign')
        with self.assertRaisesRegex(R.RehearsalError,'collision'):self.start()
        self.assertFalse(self.base.exists())

    def test_invalid_archive_fails_before_mount_or_compose(self):
        with self.assertRaises(Exception):R.start(self.engine,B,self.local,self.lock,io.BytesIO(b'bad'))
        self.engine.run.assert_not_called();self.assertFalse(self.base.exists())

    def test_failed_native_readback_cleans_only_rehearsal(self):
        with mock.patch.object(R,'native_probe',side_effect=R.RehearsalError('synthetic_native_failure')):
            with self.assertRaisesRegex(R.RehearsalError,'synthetic_native_failure'):self.start()
        self.assertFalse(self.base.exists())
        commands=[call.args[0] for call in self.engine.run.call_args_list]
        for command in commands:
            self.assertNotIn(P.PROJECT,command)
        self.assertTrue(any('down' in command for command in commands))

    def test_cleanup_failure_is_reported_and_state_preserved(self):
        with mock.patch.object(R,'native_probe',side_effect=R.RehearsalError('failed')),mock.patch.object(R,'stop',side_effect=OSError('private details')):
            with self.assertRaisesRegex(R.RehearsalError,'cleanup_needs_review'):self.start()
        self.assertTrue(self.base.exists())

    def test_health_check_alone_never_accepts_browser_and_both_counters_required(self):
        self.start()
        for login,step in [(10,42),(11,42),(10,43)]:
            with mock.patch.object(R,'native_probe',return_value={**native(),'login_events':login,'totp_max_step':step}):
                with self.assertRaisesRegex(R.RehearsalError,'browser_evidence_pending'):R.check(self.engine,self.local,accept=True)
        with mock.patch.object(R,'native_probe',return_value={**native(),'login_events':11,'totp_max_step':43}):
            result=R.check(self.engine,self.local,accept=True)
        self.assertEqual(result['browser_acceptance'],'aggregate_evidence_passed')
        self.assertEqual(result['household_readiness'],'pending')

    def test_malformed_baselines_cannot_fabricate_browser_evidence(self):
        self.start()
        for baseline in ({'login_events':True,'totp_max_step':42},{'login_events':-1,'totp_max_step':42},{'login_events':10,'totp_max_step':-2}):
            (R.CONTROL/'baseline.json').write_text(json.dumps(baseline))
            with self.assertRaisesRegex(R.RehearsalError,'baseline_invalid'):R.check(self.engine,self.local,accept=True)

    def test_control_tamper_rejected_before_docker_mutation(self):
        self.start();self.engine.reset_mock();(R.CONTROL/'compose.yaml').write_text('wrong')
        with self.assertRaisesRegex(R.RehearsalError,'compose_drift'):R.stop(self.engine,self.local)
        self.engine.run.assert_not_called()

    def test_down_without_mount_after_reboot_can_remove_verified_empty_state(self):
        self.start()
        import shutil
        for path in R.STATE.iterdir():shutil.rmtree(path) if path.is_dir() else path.unlink()
        self.mounted=False
        result=R.stop(self.engine,self.local)
        self.assertEqual(result['status'],'stopped');self.assertFalse(self.base.exists())

    def test_nonempty_unmounted_state_is_preserved(self):
        self.start();self.mounted=False
        with self.assertRaisesRegex(R.RehearsalError,'nonempty_unmounted'):R.stop(self.engine,self.local)
        self.assertTrue((R.STATE/'data/icons/item').exists())


class NativeContextTests(unittest.TestCase):
    def test_baseline_clears_native_authentik_sessions_only_and_check_is_readonly(self):
        probe=load('rehearsal_native_sessions','scripts/identity/rehearsal_probe.py')
        settings=types.SimpleNamespace(SECRET_KEY='synthetic',SESSION_COOKIE_DOMAIN=None)
        conf=types.ModuleType('django.conf');conf.settings=settings
        signing=types.SimpleNamespace(dumps=lambda value:value,loads=lambda value:value)
        core=types.ModuleType('django.core');core.signing=signing
        models=types.ModuleType('authentik.core.models');models.User=mock.Mock();models.Session=mock.Mock()
        models.User.objects.filter.return_value.exists.return_value=True
        events=types.ModuleType('authentik.events.models');events.Event=mock.Mock()
        events.Event.objects.filter.return_value.count.return_value=10
        factors=types.ModuleType('authentik.stages.authenticator_totp.models');factors.TOTPDevice=mock.Mock()
        factors.TOTPDevice.objects.filter.return_value=[types.SimpleNamespace(bin_key=b'x'*20,last_t=42)]
        with mock.patch.dict(sys.modules,{'django.conf':conf,'django.core':core,'authentik.core.models':models,
                'authentik.events.models':events,'authentik.stages.authenticator_totp.models':factors}),mock.patch.object(probe.Path,'read_text',return_value='synthetic'):
            result=probe.inspect_restored('baseline')
            self.assertTrue(result['signing_roundtrip']);self.assertTrue(result['secret_loaded'])
            models.Session.objects.all.return_value.delete.assert_called_once_with()
            models.Session.reset_mock()
            probe.inspect_restored('check')
            models.Session.objects.all.assert_not_called()

    def test_readback_uses_the_restored_ready_public_tenant(self):
        probe=load('rehearsal_native_context','scripts/identity/rehearsal_probe.py')
        events=[]
        tenant=mock.MagicMock()
        tenant.__enter__.side_effect=lambda:events.append('enter')
        tenant.__exit__.side_effect=lambda *args:events.append('exit')
        model=mock.Mock();model.objects.get.return_value=tenant
        setup=types.ModuleType('authentik.root.setup');setup.setup=mock.Mock()
        django=types.ModuleType('django');django.setup=mock.Mock()
        models=types.ModuleType('authentik.tenants.models');models.Tenant=model
        def inspect(phase):
            self.assertEqual(events,['enter']);self.assertEqual(phase,'check');return {'status':'passed'}
        with mock.patch.dict(sys.modules,{'authentik.root.setup':setup,'django':django,'authentik.tenants.models':models}),mock.patch.object(probe,'inspect_restored',side_effect=inspect):
            self.assertEqual(probe.readback('check'),{'status':'passed'})
        model.objects.get.assert_called_once_with(schema_name='public',ready=True)
        self.assertEqual(events,['enter','exit'])


class MountAndReportTests(unittest.TestCase):
    def test_low_memory_or_busy_port_stop_before_allocating(self):
        with mock.patch.object(R.Path,'read_text',return_value='MemAvailable: 1024 kB\n'),mock.patch.object(R.socket,'socket') as socket:
            with self.assertRaisesRegex(R.RehearsalError,'6_gib'):R.require_resources()
            socket.assert_not_called()
        with mock.patch.object(R.Path,'read_text',return_value='MemAvailable: 9999999 kB\n'),mock.patch.object(R.socket,'socket') as socket:
            socket.return_value.__enter__.return_value.bind.side_effect=OSError('busy')
            with self.assertRaisesRegex(R.RehearsalError,'port_busy'):R.require_resources()

    def test_foreign_or_executable_filesystem_rejected(self):
        engine=mock.Mock()
        for fstype,source,options in [('ext4','identity-rehearsal','rw,nosuid,nodev,noexec'),('tmpfs','other','rw,nosuid,nodev,noexec'),('tmpfs','identity-rehearsal','rw,nosuid,nodev')]:
            row={'target':str(R.STATE),'fstype':fstype,'source':source,'options':options}
            engine.run.return_value=(0,json.dumps({'filesystems':[row]}).encode())
            with self.assertRaisesRegex(R.RehearsalError,'unsafe_mount'):R.inspect_mount(engine)

    def test_report_cannot_upgrade_browser_or_household_acceptance(self):
        report={'status':'passed','ui_url':R.URL,'native_startup':'passed','restored_secret_signing':'passed',
                'restored_totp_readback':'passed','browser_evidence':{'new_login_event':False,'totp_step_advanced':False},
                'browser_acceptance':'pending_owner_confirmation','household_readiness':'pending','scope':R.SCOPE}
        self.assertEqual(R.validate_report(report),report)
        for change in ({'household_readiness':'passed'},{'browser_acceptance':'passed'},{'ui_url':'http://0.0.0.0:19000'},{'scope':'private details'}):
            with self.assertRaises(R.RehearsalError):R.validate_report({**report,**change})


if __name__=='__main__':unittest.main()
