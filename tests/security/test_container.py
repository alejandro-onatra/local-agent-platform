"""Unsafe runtime mutations must fail; unimplemented household acceptance stays pending."""
import copy
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import yaml
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('container_check', ROOT/'scripts/security/check-container.py')
MOD = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = ROOT/'artifacts/openhands/projects'
        self.expected_image = yaml.safe_load((ROOT/'infra/openhands/versions.yaml').read_text())['image']
        self.info = {'running':True,'user':'1000:1000','caps_drop':['ALL'],'caps_add':[],
                     'security_opt':['no-new-privileges:true'],'apparmor':'docker-default',
                     'privileged':False,'memory':6*1024**3,'cpus':4*10**9,'pids':512,
                     'readonly':True,'ports':{},'networks':{MOD.PROJECT+'_agent-link':{}},
                     'mounts':[{'Destination':'/projects','Type':'bind','Source':str(self.workspace)},
                               {'Destination':'/home/openhands/.openhands','Type':'volume','Name':MOD.PROJECT+'_openhands-state','Source':'/var/lib/docker/volumes/synthetic'}],
                     'logging':{'Type':'json-file','Config':{'max-size':'10m','max-file':'3'}}}
        self.proc = {'uid':1000,'pid1_uid':1000,'cap_eff':0,'cap_bnd':0,'no_new_privs':1,'seccomp':2,
                     'apparmor_enforcing':True,'host_canary_denied':True,'workspace_writable':True,'state_writable':True,'config_writable':True,
                     'cgroup':{'memory.max':str(6*1024**3),'cpu.max':'400000 100000','pids.max':'512'}}

    def evaluate(self):
        return MOD.assess(self.info,self.proc,{'Internal':True},[self.expected_image],self.workspace,
                          expected_image=self.expected_image)

    def test_clean_baseline_is_not_family_acceptance(self):
        r=self.evaluate();self.assertEqual(r['baseline'],'passed');self.assertEqual(r['household_readiness'],'pending')
        self.assertIn('live.disk_limits',r['pending_acceptance'])

    def test_root_or_pid1_root_rejected(self):
        for field in ('uid','pid1_uid'):
            with self.subTest(field=field):
                old=self.proc[field];self.proc[field]=0
                self.assertEqual(self.evaluate()['checks']['runtime.nonroot']['status'],'failed')
                self.proc[field]=old

    def test_capabilities_filters_and_no_new_privs_rejected(self):
        for field,value,check in [('cap_eff',1,'runtime.capabilities'),('cap_bnd',1,'runtime.capabilities'),
                                  ('no_new_privs',0,'runtime.no_new_privileges'),('seccomp',0,'runtime.seccomp'),
                                  ('apparmor_enforcing',False,'runtime.apparmor')]:
            old=self.proc[field];self.proc[field]=value
            self.assertEqual(self.evaluate()['checks'][check]['status'],'failed');self.proc[field]=old

    def test_gpu_and_host_namespace_rejected(self):
        for field,value in [('device_requests',[{'Driver':'nvidia'}]),('pid_mode','host'),('privileged',True)]:
            old=self.info.get(field);self.info[field]=value
            self.assertEqual(self.evaluate()['checks']['runtime.namespaces_devices']['status'],'failed')
            self.info[field]=old

    def test_extra_mount_or_other_workspace_rejected(self):
        original=copy.deepcopy(self.info['mounts'])
        self.info['mounts'].append({'Destination':'/host','Type':'bind','Source':'/'})
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'failed')
        self.info['mounts']=original;self.info['mounts'][0]['Source']='/home/other'
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'failed')

    def test_expected_tmpfs_mounts_are_allowed_but_unknown_paths_rejected(self):
        self.info['mounts'] += [{'Destination':path,'Type':'tmpfs','Source':''}
                               for path in ['/tmp','/home/openhands/workspace','/home/openhands/.cache','/home/openhands/.config']]
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'passed')
        self.info['mounts'].append({'Destination':'/other','Type':'tmpfs','Source':''})
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'failed')

    def test_backend_launcher_requires_exact_source_and_readonly_bind(self):
        launcher = {'Destination':'/usr/local/bin/openhands-agent-server','Type':'bind',
                    'Source':str(ROOT/'scripts/openhands/start-agent-server.py'),'RW':False}
        self.info['mounts'].append(launcher)
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'passed')
        launcher['RW']=True
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'failed')
        launcher['RW']=False;launcher['Source']='/home/other/launcher.py'
        self.assertEqual(self.evaluate()['checks']['runtime.mount_allowlist']['status'],'failed')

    def test_extra_network_and_ports_rejected(self):
        self.info['networks']['unexpected']={}
        self.assertEqual(self.evaluate()['checks']['runtime.internal_network']['status'],'failed')
        self.info['networks'].pop('unexpected');self.info['ports']={'8000/tcp':[{'HostIp':'0.0.0.0'}]}
        self.assertEqual(self.evaluate()['checks']['runtime.internal_network']['status'],'failed')

    def test_effective_cgroups_unbounded_or_missing_rejected(self):
        for field,value in [('memory.max','max'),('pids.max',None),('cpu.max','max 100000'),('cpu.max','400000 0')]:
            old=self.proc['cgroup'][field];self.proc['cgroup'][field]=value
            self.assertEqual(self.evaluate()['checks']['runtime.memory_cpu_pids']['status'],'failed')
            self.proc['cgroup'][field]=old

    def test_host_inspect_cgroups_mismatch_rejected(self):
        self.info['memory']=0
        self.assertEqual(self.evaluate()['checks']['runtime.memory_cpu_pids']['status'],'failed')

    def test_writable_root_is_not_approved(self):
        self.info['readonly']=False
        self.assertEqual(self.evaluate()['checks']['runtime.readonly_root']['status'],'failed')

    def test_canary_visible_or_allowed_write_broken_rejected(self):
        self.proc['host_canary_denied']=False
        self.assertEqual(self.evaluate()['checks']['runtime.host_file_canary_denied']['status'],'failed')
        self.proc['workspace_writable']=False
        self.assertEqual(self.evaluate()['checks']['runtime.allowed_writes']['status'],'failed')

    def test_blocked_runtime_configuration_write_fails_compatibility(self):
        self.proc['config_writable']=False
        self.assertEqual(self.evaluate()['checks']['runtime.allowed_writes']['status'],'failed')
        self.proc.pop('config_writable')
        self.assertEqual(self.evaluate()['checks']['runtime.allowed_writes']['status'],'failed')

    def test_sensitive_input_is_not_echoed(self):
        marker='synthetic-sensitive-marker';self.info['unrelated_secret']=marker
        self.info['mounts'][0]['Source']='/'+marker
        self.assertNotIn(marker,json.dumps(self.evaluate()))

    def test_wrong_image_rejected(self):
        r=MOD.assess(self.info,self.proc,{'Internal':True},['example.invalid/other@sha256:'+'0'*64],self.workspace,
                     expected_image=self.expected_image)
        self.assertEqual(r['checks']['runtime.running_pinned_image']['status'],'failed')


    def test_previous_release_does_not_satisfy_current_lock(self):
        lock = yaml.safe_load((ROOT/'infra/openhands/versions.yaml').read_text())
        self.assertNotEqual(lock['image'], lock['upgrade_from']['image'])
        r = MOD.assess(self.info, self.proc, {'Internal':True},
                       [lock['upgrade_from']['image']], self.workspace,
                       expected_image=MOD.load_expected_image())
        self.assertEqual(r['checks']['runtime.running_pinned_image']['status'], 'failed')

    def test_collect_uses_current_deployment_lock_for_image_assessment(self):
        self.info['image'] = 'sha256:'+'1'*64
        state = {'running':True,'status':'running','exit_code':0,'oom_killed':False}
        responses = ['29.0', 'one', json.dumps(state), json.dumps(self.info),
                     json.dumps(self.proc), json.dumps({'Internal':True}),
                     json.dumps([self.expected_image])]
        with mock.patch.object(MOD,'run',side_effect=responses):
            result = MOD.collect(['docker','--context','default'])
        self.assertEqual(result['checks']['runtime.running_pinned_image']['status'], 'passed')


class ImageLockTests(unittest.TestCase):
    def test_lock_change_is_read_without_reimporting_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory)/'versions.yaml'
            for digest in ('a'*64, 'b'*64):
                expected = 'ghcr.io/openhands/agent-canvas@sha256:'+digest
                lock.write_text(yaml.safe_dump({'image':expected}))
                self.assertEqual(MOD.load_expected_image(lock), expected)

    def test_invalid_or_mutable_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory)/'versions.yaml'
            for content in ('image: ghcr.io/openhands/agent-canvas:latest\n',
                            'image: ghcr.io/openhands/agent-canvas@sha256:bad\n',
                            'image: example.invalid/other@sha256:'+'a'*64+'\n',
                            'image: [unterminated', '{}', 'null', '[]', 'image: 42'):
                lock.write_text(content)
                with self.subTest(content=content), self.assertRaises(MOD.ProbeFailure) as caught:
                    MOD.load_expected_image(lock)
                self.assertEqual(caught.exception.code, 'image_lock_invalid')
            lock.unlink()
            with self.assertRaises(MOD.ProbeFailure) as caught:
                MOD.load_expected_image(lock)
            self.assertEqual(caught.exception.code, 'image_lock_invalid')

    def test_invalid_lock_prevents_docker_probes(self):
        with mock.patch.object(MOD,'load_expected_image',side_effect=MOD.ProbeFailure('image_lock_invalid')), \
                mock.patch.object(MOD,'run') as run:
            with self.assertRaises(MOD.ProbeFailure):
                MOD.collect(['docker','--context','default'])
            run.assert_not_called()



class DiscoveryTests(unittest.TestCase):
    docker = ['docker','--context','default']

    def test_docker_access_failure_has_fixed_category(self):
        with mock.patch.object(MOD,'run',side_effect=RuntimeError('synthetic-sensitive-marker')):
            with self.assertRaises(MOD.ProbeFailure) as caught: MOD.collect(self.docker)
        self.assertEqual(caught.exception.code,'docker_access_unavailable')

    def test_missing_agent_is_distinct_from_stopped(self):
        with mock.patch.object(MOD,'run',side_effect=['29.0','']) as run:
            with self.assertRaises(MOD.ProbeFailure) as caught: MOD.collect(self.docker)
        self.assertEqual(caught.exception.code,'agent_not_found')
        self.assertIn('-a',run.call_args.args[1])

    def test_ambiguous_agents_cannot_be_selected(self):
        with mock.patch.object(MOD,'run',side_effect=['29.0','one two']):
            with self.assertRaises(MOD.ProbeFailure) as caught: MOD.collect(self.docker)
        self.assertEqual(caught.exception.code,'agent_selection_ambiguous')

    def test_stopped_or_paused_agent_does_not_execute_probe(self):
        for status,running in [('exited',False),('created',False),('paused',True),('restarting',True)]:
            state={'running':running,'status':status,'exit_code':0,'oom_killed':False}
            with self.subTest(status=status),mock.patch.object(MOD,'run',side_effect=['29.0','one',json.dumps(state)]) as run:
                with self.assertRaises(MOD.ProbeFailure) as caught: MOD.collect(self.docker)
                self.assertEqual(caught.exception.code,'agent_not_running')
                self.assertEqual(caught.exception.state,state)
                self.assertEqual(run.call_count,3)

    def test_unexpected_state_content_cannot_be_reported(self):
        state={'running':False,'status':'synthetic-sensitive-marker','exit_code':0,'oom_killed':False}
        with mock.patch.object(MOD,'run',side_effect=['29.0','one',json.dumps(state)]):
            with self.assertRaises(MOD.ProbeFailure) as caught: MOD.collect(self.docker)
        self.assertEqual(caught.exception.code,'agent_state_unavailable')
        self.assertIsNone(caught.exception.state)

    def test_cli_fixed_error_does_not_leak_exception(self):
        for failure in [MOD.ProbeFailure('agent_not_found'),RuntimeError('synthetic-sensitive-marker')]:
            output=io.StringIO()
            with mock.patch('sys.argv',['check-container.py']),mock.patch.object(MOD,'collect',side_effect=failure),mock.patch.object(MOD,'save',return_value='synthetic-report'),contextlib.redirect_stdout(output):
                self.assertEqual(MOD.main(),1)
            self.assertNotIn('synthetic-sensitive-marker',output.getvalue())
            self.assertIn('"household_readiness": "pending"',output.getvalue())


if __name__=='__main__': unittest.main()
