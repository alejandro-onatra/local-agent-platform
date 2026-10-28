"""Fail-closed disposable orchestration tests; native execution is a separate task."""
import contextlib
import copy
import io
import importlib.util
import json
import logging
import os
import subprocess
import sys
import types
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import yaml

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('identity_native_probe',ROOT/'scripts/identity/native-check.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

native_spec=importlib.util.spec_from_file_location('native_startup',ROOT/'scripts/identity/native_validate.py')
N=importlib.util.module_from_spec(native_spec);native_spec.loader.exec_module(N)

class StartupTests(unittest.TestCase):
    def setUp(self):self.addCleanup(logging.disable,logging.root.manager.disable)
    def test_mounted_script_needs_source_root_and_official_setup_before_django(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);candidate=base/'candidate';candidate.mkdir()
            packages=base/'image-source';(packages/'authentik/root').mkdir(parents=True);(packages/'django').mkdir()
            (packages/'authentik/__init__.py').touch();(packages/'authentik/root/__init__.py').touch()
            (packages/'authentik/root/setup.py').write_text('import os\ndef setup(): os.environ["PROBE_SETUP_DONE"]="1"\n')
            (packages/'django/__init__.py').write_text('import os\ndef setup(): assert os.environ.get("PROBE_SETUP_DONE")=="1"\n')
            script=candidate/'probe.py'
            script.write_text('import importlib.util\ns=importlib.util.spec_from_file_location("native",'+repr(str(ROOT/'scripts/identity/native_validate.py'))+')\nm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nm.initialize()\nprint("initialized")\n')
            env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
            before=subprocess.run([sys.executable,'-B',str(script)],cwd=candidate,env=env,capture_output=True,timeout=5)
            self.assertNotEqual(before.returncode,0)
            after=subprocess.run([sys.executable,'-B',str(script)],cwd=candidate,env=env|{'PYTHONPATH':str(packages)},capture_output=True,timeout=5)
            self.assertEqual(after.returncode,0);self.assertEqual(after.stdout.strip(),b'initialized')
    def test_native_execute_uses_official_lifecycle_migrations_after_setup(self):
        calls=[]
        def migrate():calls.append('migrate');raise RuntimeError('stop_after_migration_call')
        modules={'lifecycle.migrate':types.SimpleNamespace(run_migrations=migrate),
                 'authentik.tenants.models':types.SimpleNamespace(Tenant=mock.Mock()),
                 'authentik.blueprints.v1.importer':types.SimpleNamespace(Importer=mock.Mock())}
        with mock.patch.dict(sys.modules,modules),mock.patch.object(N,'initialize',side_effect=lambda:calls.append('initialize')):
            with self.assertRaisesRegex(RuntimeError,'stop_after_migration_call'):N.execute()
        self.assertEqual(calls,['initialize','migrate']);self.assertEqual(N.stage,'migrations')
    def test_main_redacts_exception_values_and_reports_fixed_category(self):
        for error,reason in [(ModuleNotFoundError('PRIVATE-CANARY /secret/file'),'module_missing'),
                             (PermissionError('PRIVATE-CANARY'),'permission_denied'),
                             (RuntimeError('PRIVATE-CANARY'),'other')]:
            with self.subTest(category=reason),mock.patch.object(N,'execute',side_effect=error),contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(N.main(),1)
            value=output.getvalue();self.assertNotIn('PRIVATE-CANARY',value);self.assertNotIn('/secret/file',value)
            data=json.loads(value.split('=',1)[1]);self.assertEqual(data['diagnostic'],reason)
            self.assertEqual(data['stage'],'django_setup')
    def test_failure_diagnostics_are_allowlisted_by_host_parser(self):
        raw=b'IDENTITY_NATIVE_RESULT={"status":"failed","stage":"django_setup","diagnostic":"module_missing"}'
        with self.assertRaisesRegex(P.CheckError,'native_failed_django_setup_module_missing'):P.native_result(raw,1)
        bad=raw.replace(b'module_missing',b'PRIVATE-CANARY')
        with self.assertRaisesRegex(P.CheckError,'^invalid_native_result$'):P.native_result(bad,1)

class NativeValidationErrorsTests(unittest.TestCase):
    def setUp(self):self.addCleanup(logging.disable,logging.root.manager.disable)
    def importer(self):
        row=types.SimpleNamespace(id='outpost',attrs={'type':'proxy','service_connection':None},identifiers={'name':'fixed'})
        return mock.Mock(blueprint=types.SimpleNamespace(entries=[row]))
    def test_typed_validation_error_survives_logging_suppression_without_text(self):
        importer=self.importer()
        error=type('EntryInvalidError',(ValueError,),{})('PRIVATE-CANARY /secret/path')
        error.entry_id='outpost'
        error.validation_error=types.SimpleNamespace(get_codes=lambda:{'type':['required'],'PRIVATE-FIELD':['PRIVATE-CODE']})
        importer.validate.side_effect=error
        def execute():
            N.stage='native_validation';N.validate_native(importer)
        with mock.patch.object(N,'execute',side_effect=execute),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(N.main(),1)
        importer.validate.assert_called_once_with(raise_validation_errors=True)
        value=output.getvalue();self.assertNotIn('PRIVATE',value);self.assertNotIn('/secret/path',value)
        result=json.loads(value.split('=',1)[1])
        self.assertEqual(result['entry'],'outpost');self.assertEqual(result['diagnostic'],'blueprint_rejected')
        self.assertEqual(result['issues'],[{'field':'type','code':'required'}])
    def test_unknown_entry_fields_and_codes_never_escape(self):
        importer=self.importer()
        error=ValueError('PRIVATE-CANARY');error.entry_id='unknown-private'
        error.validation_error=types.SimpleNamespace(get_codes=lambda:{'type':['PRIVATE-CODE']})
        self.assertEqual(N.validation_summary(error,importer.blueprint.entries),(None,[]))
        error.entry_id='outpost'
        self.assertEqual(N.validation_summary(error,importer.blueprint.entries),('outpost',[]))
    def test_false_or_nonboolean_validation_result_is_rejected(self):
        for value in (False,None,1,'true'):
            with self.subTest(value=value):
                importer=self.importer();importer.validate.return_value=(value,[])
                with self.assertRaises(AssertionError):N.validate_native(importer)
        importer=self.importer();importer.validate.return_value=(True,[]);N.validate_native(importer)
    def test_host_parser_only_accepts_known_fields_and_fixed_codes(self):
        result={'status':'failed','stage':'native_validation','entry':'outpost','diagnostic':'blueprint_rejected',
                'issues':[{'field':'type','code':'required'}]}
        def encoded():return b'IDENTITY_NATIVE_RESULT='+json.dumps(result).encode()
        with self.assertRaises(P.CheckError) as exc:P.native_result(encoded(),1)
        self.assertEqual(exc.exception.issues,result['issues'])
        for issue in ({'field':'private-field','code':'required'},{'field':'type','code':'PRIVATE-CODE'},
                      {'field':'type','code':'required','value':'PRIVATE-CANARY'}):
            result['issues']=[issue]
            with self.assertRaisesRegex(P.CheckError,'^invalid_native_result$'):P.native_result(encoded(),1)


class NativeProbeTests(unittest.TestCase):
    def test_pinned_bundle_renders_only_isolated_temporary_mounts(self):
        lock,raw=P.bundle();value=yaml.safe_load(P.render(raw,lock,Path('/tmp/private'),Path('/tmp/public')))
        self.assertEqual(value['networks'],{'validation':{'internal':True}})
        for service in value['services'].values():
            self.assertNotIn('ports',service);self.assertNotIn('privileged',service)
            self.assertEqual(service['networks'],['validation'])
            self.assertIn('@sha256:',service['image'])
            self.assertTrue(all(v['source'].startswith('/tmp/') for v in service['volumes']))
        self.assertEqual(value['services']['checker']['environment']['PYTHONPATH'],'/')
        self.assertNotIn('volumes',value)
        self.assertIn('/var/lib/postgresql:',value['services']['database']['tmpfs'][0])
    def test_source_mutations_fail_before_docker(self):
        _,raw=P.bundle();original=yaml.safe_load(raw)
        changes=[lambda c:c['services']['checker'].update(ports=['0.0.0.0:9000:9000']),
                 lambda c:c['services']['checker'].update(user='0:0'),
                 lambda c:c['networks']['validation'].update(internal=False),
                 lambda c:c['services']['database'].update(mem_limit='100g'),
                 lambda c:c['services']['checker']['volumes'][0].update(source='/home/private'),
                 lambda c:c['services']['checker']['environment'].update(AUTHENTIK_SECRET_KEY='plaintext'),
                 lambda c:c['services']['database'].update(tmpfs=[])]
        for change in changes:
            with self.subTest(change=changes.index(change)),tempfile.TemporaryDirectory() as folder:
                value=copy.deepcopy(original);change(value)
                path=Path(folder)/'compose.yaml';path.write_text(yaml.safe_dump(value))
                with mock.patch.object(P,'TEMPLATE',path):
                    with self.assertRaises(P.CheckError):P.bundle()
    def test_tag_swapped_repository_and_wrong_version_locks_rejected(self):
        original,_=P.bundle()
        for field,value in [('image','ghcr.io/goauthentik/server:latest'),('image','other@sha256:'+'a'*64),('version','other')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
                lock=copy.deepcopy(original);lock['authentik'][field]=value
                path=Path(folder)/'lock.yaml';path.write_text(yaml.safe_dump(lock))
                with mock.patch.object(P,'LOCK',path):
                    with self.assertRaises(P.CheckError):P.bundle()
    def test_result_requires_exact_sentinel_success_and_zero_exit(self):
        success=b'IDENTITY_NATIVE_RESULT={"status":"passed","stage":"completed"}'
        self.assertEqual(P.native_result(success,0)['status'],'passed')
        for output,code in [(b'',0),(success,1),(success+b'\n'+success,0),
                            (b'IDENTITY_NATIVE_RESULT={"status":"passed","stage":"migrations"}',0),
                            (b'IDENTITY_NATIVE_RESULT={"status":"failed","stage":"native_import"}',0),
                            (b'IDENTITY_NATIVE_RESULT={"status":"passed","stage":"completed","secret":"hidden"}',0)]:
            with self.subTest(output=output[:30],code=code):
                with self.assertRaises(P.CheckError):P.native_result(output,code)
    def exercise(self,mode=None):
        lock,raw=P.bundle();temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        folder=Path(temp.name)/'run';folder.mkdir();calls=[];attempted=False;configs=[]
        class Engine:
            def run(self,args,**kwargs):
                nonlocal attempted
                calls.append(args)
                if 'run' in args:
                    attempted=True
                    if mode=='timeout':raise P.CheckError('docker_command_timeout')
                    if mode=='native_fail':return 1,b'IDENTITY_NATIVE_RESULT={"status":"failed","stage":"native_readback"}'
                    return 0,b'IDENTITY_NATIVE_RESULT={"status":"passed","stage":"completed"}'
                if args[0]=='ps':
                    if 'collision'==mode and not attempted:return 0,b'a'*64
                    return 0,b'a'*64 if attempted else b''
                if 'up' in args:
                    configs.append((folder/'compose.yaml').read_text())
                    for name,uid in [('postgres-password',70),('authentik-password',1000),('authentik-secret',1000)]:
                        self_test.assertEqual((folder/'private'/name).stat().st_mode&0o777,0o400)
                    if mode=='start_fail':raise P.CheckError('docker_command_failed')
                if 'down' in args and mode=='cleanup_fail':raise P.CheckError('docker_command_failed')
                return 0,b''
        self_test=self
        with mock.patch.object(P.os,'geteuid',return_value=0),mock.patch.object(P.os,'fchown'), \
             mock.patch.object(P.tempfile,'mkdtemp',return_value=str(folder)), \
             mock.patch.object(P.Path,'read_text',autospec=True,side_effect=lambda path,*a,**kw:'MemAvailable: 8388608 kB\n' if str(path)=='/proc/meminfo' else original_read(path,*a,**kw)):
            if mode:
                with self.assertRaises(P.CheckError) as exc:P.execute(Engine(),lock,raw)
                result=str(exc.exception)
                self.assertEqual(exc.exception.cleanup,'pending' if mode=='cleanup_fail' else 'completed')
            else:result=P.execute(Engine(),lock,raw)
        for args in calls:
            self.assertFalse(any('file://' in arg or 'PASSWORD=' in arg for arg in args))
        self.assertEqual(folder.exists(),mode=='cleanup_fail')
        return result,calls,configs
    def test_success_cleans_project_files_and_keeps_household_pending(self):
        result,calls,configs=self.exercise()
        self.assertEqual(result['status'],'passed');self.assertEqual(result['household_readiness'],'pending')
        self.assertEqual(sum('down' in args for args in calls),1)
        self.assertEqual(sum(args[0]=='rm' for args in calls),1)
        self.assertEqual(len(configs),1)
        for args in calls:
            if '--project-name' in args:self.assertRegex(args[args.index('--project-name')+1],'^'+P.PREFIX+'[a-f0-9]{32}$')
    def test_native_failure_and_timeout_still_cleanup(self):
        for mode in ('native_fail','timeout'):
            with self.subTest(mode=mode):
                result,calls,_=self.exercise(mode)
                self.assertIn('failed' if mode=='native_fail' else 'timeout',result)
                self.assertTrue(any('down' in args for args in calls))
    def test_failed_start_still_cleans_without_selecting_unrelated_container(self):
        _,calls,_=self.exercise('start_fail')
        self.assertFalse(any(args[0]=='rm' for args in calls))
        self.assertTrue(any('down' in args for args in calls))
    def test_collision_never_stops_foreign_resources(self):
        _,calls,_=self.exercise('collision')
        self.assertFalse(any('up' in args or 'down' in args or args[0]=='rm' for args in calls))
    def test_cleanup_failure_retains_private_directory_and_fails(self):
        result,_,_=self.exercise('cleanup_fail');self.assertTrue(result.startswith('cleanup_failed_'+P.PREFIX))
    def test_low_memory_stops_before_docker(self):
        engine=mock.Mock()
        with mock.patch.object(P.os,'geteuid',return_value=0),mock.patch.object(P.Path,'read_text',return_value='MemAvailable: 1000 kB\n'):
            with self.assertRaisesRegex(P.CheckError,'less_than_4_gib_available'):P.execute(engine,{},'')
        engine.run.assert_not_called()
    def test_engine_timeout_kills_and_reaps_local_process_group(self):
        process=mock.Mock(pid=12345);process.poll.return_value=None
        with mock.patch.object(P.subprocess,'Popen',return_value=process), \
             mock.patch.object(P.time,'monotonic',side_effect=[0,2]),mock.patch.object(P.os,'killpg') as kill:
            with self.assertRaisesRegex(P.CheckError,'docker_command_timeout'):P.Engine().run(['info'],timeout=1)
        kill.assert_called_once_with(12345,P.signal.SIGKILL);process.wait.assert_called_once()

    def test_nonroot_stops_before_docker(self):
        engine=mock.Mock()
        with mock.patch.object(P.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(P.CheckError,'host_admin_required'):P.execute(engine,{},'')
        engine.run.assert_not_called()

original_read=Path.read_text
if __name__=='__main__':unittest.main()
