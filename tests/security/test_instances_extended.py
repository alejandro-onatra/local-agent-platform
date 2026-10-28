"""Protocol and lifecycle failures must not become security passes or delete other data."""
import contextlib
import copy
import errno
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import uuid

ROOT=Path(__file__).resolve().parents[2]

def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/instances'/filename)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result
    level=logging.root.manager.disable
    try:spec.loader.exec_module(result)
    finally:logging.disable(level)
    return result

P=module('extended_pilot','instances.py')
N=module('extended_network_probe','network_probe.py')
W=module('extended_websocket_probe','websocket_probe.py')
I=module('extended_isolation','isolation.py')
R=module('extended_recovery','recovery.py')


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.target={'address':'172.18.0.2','port':8000}
        self.data={'own':{'address':'172.19.0.3','port':8080},'foreign':[self.target.copy() for _ in range(3)]}
    def test_only_selected_private_ipv4_and_known_service_ports_allowed(self):
        for address,port in [('8.8.8.8',8000),('127.0.0.1',8000),('::1',8000),('172.18.0.2',22),('0.0.0.0',8000)]:
            with self.assertRaises(ValueError):N.validate_target({'address':address,'port':port})
    def test_refusal_routing_denial_and_timeout_are_not_unexpected_io_errors(self):
        for code in (errno.ECONNREFUSED,errno.EHOSTUNREACH,errno.ENETUNREACH,errno.ETIMEDOUT,errno.EACCES):
            self.assertFalse(N.reachable(self.target,mock.Mock(side_effect=OSError(code,'withheld'))))
        with self.assertRaises(OSError):N.reachable(self.target,mock.Mock(side_effect=OSError(errno.EIO,'withheld')))
    def test_peer_listener_reachability_fails_denial_and_own_listener_is_required(self):
        all_open=mock.MagicMock()
        result=N.check(self.data,all_open)
        self.assertTrue(result['own_ingress_reachable']);self.assertFalse(result['peer_agent_denied'])
        all_closed=mock.Mock(side_effect=OSError(errno.ECONNREFUSED,'closed'))
        self.assertFalse(N.check(self.data,all_closed)['own_ingress_reachable'])
    def test_host_positive_control_cannot_count_dead_target_as_isolated(self):
        with self.assertRaises(P.PilotError):I.host_control(P,self.target,connect=mock.Mock(side_effect=OSError))
    def test_strict_result_rejects_fake_missing_or_string_success(self):
        tenant=P.store.load_policy()['tenants'][0]
        for result in ({},{'a':'true'},{'a':1},{'a':False},{'a':True,'extra':True}):
            with self.assertRaises(P.PilotError):I.checked_result(P,result,('a',),'fixed',tenant)
    def test_orchestrator_uses_actual_exec_and_positive_controls_before_and_after(self):
        policy=P.store.load_policy();engine=mock.Mock()
        result={name:True for name in ('own_ingress_reachable','peer_agent_denied','peer_backend_ingress_denied','peer_frontend_ingress_denied')}
        engine.run.return_value=json.dumps(result).encode()
        with mock.patch.object(P,'health'),mock.patch.object(P,'runtime'),mock.patch.object(P,'selected',return_value='a'*64), \
             mock.patch.object(I,'network_target',return_value=self.target),mock.patch.object(I,'host_control') as host:
            report=I.network_check(P,policy,{},engine)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['household_readiness'],'pending')
        self.assertEqual(host.call_count,12);self.assertEqual(engine.run.call_count,2)
        self.assertTrue(all(call.args[0][3]=='exec' for call in engine.run.call_args_list))
        self.assertNotIn('172.18.0.2',json.dumps(report))

    def test_dead_positive_target_reports_only_fixed_target_identity(self):
        policy=P.store.load_policy();engine=mock.Mock()
        with mock.patch.object(P,'health'),mock.patch.object(P,'runtime'), \
             mock.patch.object(I,'network_target',return_value=self.target), \
             mock.patch.object(I,'host_control',side_effect=P.PilotError('network_target_positive_control_failed')):
            with self.assertRaises(P.PilotError) as error:I.network_check(P,policy,{},engine)
        self.assertEqual(error.exception.details,{'tenant':'probe-a','target':'agent','probe_phase':'before'})
        self.assertNotIn(self.target['address'],str(error.exception.details))

    def test_failed_result_names_are_fixed_not_untrusted_peer_fields(self):
        tenant=P.store.load_policy()['tenants'][0]
        with self.assertRaises(P.PilotError) as error:I.checked_result(P,{'private-untrusted-value':True},('allowed_control',),'fixed',tenant)
        self.assertEqual(error.exception.details['failed_checks'],['allowed_control'])
        self.assertNotIn('private-untrusted-value',str(error.exception.details))


class Closed(Exception):
    def __init__(self,code):self.rcvd=types.SimpleNamespace(code=code)


class Socket:
    def __init__(self,url,data,mode):self.url=url;self.data=data;self.mode=mode;self.auth=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def send(self,body):self.auth=json.loads(body)
    def recv(self,timeout):
        if self.mode=='timeout':raise TimeoutError('private details withheld')
        if self.mode=='unauth_sync':return '{"type":"sync"}'
        if self.auth['session_api_key']!=self.data['own_key']:raise Closed(4001)
        if self.data['foreign_id'] in self.url:raise Closed(4004)
        if self.mode=='server_error':raise Closed(1011)
        return '{"type":"sync","through_seq":null}'


class WebSocketTests(unittest.TestCase):
    def setUp(self):
        self.data={'own_id':str(uuid.uuid4()),'foreign_id':str(uuid.uuid4()),'own_key':'a'*64,'foreign_key':'b'*64}
    def connect(self,mode='normal'):
        def call(url,**kwargs):
            self.assertTrue(url.startswith('ws://ingress:8080/sockets/session/'))
            self.assertNotIn('?',url)
            self.assertNotIn(self.data['own_key'],url+str(kwargs))
            return Socket(url,self.data,mode)
        return call
    def test_native_sync_and_exact_denial_codes_pass_without_uri_credentials(self):
        self.assertTrue(all(W.check(self.data,self.connect(),Closed).values()))
    def test_upgrade_and_sync_without_auth_is_not_a_security_pass(self):
        result=W.check(self.data,self.connect('unauth_sync'),Closed)
        self.assertFalse(result['anonymous_rejected']);self.assertFalse(result['foreign_key_rejected'])
    def test_server_error_is_not_authentication_denial(self):
        self.assertFalse(W.check(self.data,self.connect('server_error'),Closed)['own_authenticated_sync'])
    def test_timeout_is_not_silently_classified_as_denial(self):
        with self.assertRaises(TimeoutError):W.check(self.data,self.connect('timeout'),Closed)
    def test_invalid_or_shared_native_keys_and_ids_are_rejected(self):
        for mutation in ({'own_key':'bad'},{'foreign_key':'a'*64},{'foreign_id':self.data['own_id']},{'own_id':'../../private'}):
            with self.assertRaises(ValueError):W.validate(self.data|mutation)
    def test_client_keys_only_on_stdin_no_state_mount_and_probe_cleanup(self):
        policy=P.store.load_policy();keys=[self.data['own_key'],self.data['foreign_key']]
        app={t['id']:set() for t in policy['tenants']}
        def request(tenant,path,key=None,method='GET',body=None):
            if method=='POST':app[tenant['id']].add(body['conversation_id']);return 201,b'{}'
            identifier=path.rsplit('/',1)[-1]
            if method=='DELETE':app[tenant['id']].discard(identifier);return 200,b'{}'
            return (200 if identifier in app[tenant['id']] else 404),b'{}'
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs))
            if args[3]=='rm':return b''
            return json.dumps({k:True for k in ('own_authenticated_sync','anonymous_rejected','foreign_key_rejected','foreign_conversation_denied')}).encode()
        engine=mock.Mock();engine.run.side_effect=run
        lock=P.store.read_yaml(ROOT/'infra/openhands/versions.yaml')
        with mock.patch.object(P,'health',return_value=keys),mock.patch.object(P,'runtime'),mock.patch.object(P,'request',side_effect=request):
            result=I.websocket_check(P,policy,lock,engine)
        self.assertEqual(result['status'],'passed');self.assertTrue(all(not rows for rows in app.values()))
        for args,kwargs in calls:
            self.assertNotIn(keys[0],str(args));self.assertNotIn(keys[1],str(args))
            if args[3]=='run':
                self.assertNotIn('--mount',args);self.assertIn(keys[0].encode(),kwargs['input'])
        self.assertEqual(sum(args[3]=='rm' for args,_ in calls),2)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.policy=P.store.load_policy();self.records=R.make_records(self.policy)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
    def test_manifest_rejects_paths_real_keys_extra_fields_and_duplicate_identity(self):
        good={'schema_version':1,'purpose':'synthetic_application_recovery','records':self.records}
        for modify in [lambda d:d['records'][0].update(marker='../../private'),
                       lambda d:d['records'][0].update(value='real-provider-key'),
                       lambda d:d['records'][0].update(secret_name='PRODUCTION_SECRET'),
                       lambda d:d['records'][0].update(native_key='a'*64),
                       lambda d:d['records'][1].update(tenant='probe-a')]:
            data=copy.deepcopy(good);modify(data)
            with self.assertRaises(ValueError):R.validate_manifest(data,self.policy)
    def test_manifest_integrity_and_permissions_fail_before_restore(self):
        api=types.SimpleNamespace(BASE=self.base,store=types.SimpleNamespace(safe_path=mock.Mock()),PilotError=P.PilotError)
        path,digest=R.snapshot(api,self.policy,self.records)
        self.assertEqual(len(R.read_snapshot(api,self.policy,path,digest,owner=os.getuid())),2)
        path.chmod(0o644)
        with self.assertRaises(P.PilotError):R.read_snapshot(api,self.policy,path,digest,owner=os.getuid())
        path.chmod(0o600);path.write_text(path.read_text()+' ')
        with self.assertRaises(P.PilotError):R.read_snapshot(api,self.policy,path,digest,owner=os.getuid())
    def test_marker_reader_rejects_symlink_and_does_not_remove_changed_file(self):
        tenant={'uid':os.getuid(),'gid':os.getgid()};record=self.records[0]
        state=self.base/'state';workspace=self.base/'workspace';state.mkdir();workspace.mkdir()
        api=types.SimpleNamespace(paths=lambda t:(state,workspace,self.base),PilotError=P.PilotError)
        tracked=[];R.create_markers(api,tenant,record,tracked)
        self.assertTrue(all(R.marker_matches(path,tenant,record) for path in tracked))
        tracked[0].write_text('different')
        with self.assertRaises(P.PilotError):R.remove_markers(api,tenant,record,tracked)
        self.assertTrue(tracked[0].exists())
        tracked[0].unlink();tracked[0].symlink_to('/etc/passwd')
        with self.assertRaises(OSError):R.marker_matches(tracked[0],tenant,record)
    def exercise(self,mode=None):
        policy=copy.deepcopy(self.policy)
        for tenant in policy['tenants']:tenant.update(uid=os.getuid(),gid=os.getgid())
        paths={}
        for tenant in policy['tenants']:
            state=self.base/tenant['id']/'state';workspace=self.base/tenant['id']/'workspace'
            state.mkdir(parents=True);workspace.mkdir()
            paths[tenant['id']]=(state,workspace,self.base)
        app={t['id']:{'secrets':{'KEEP_REAL_DATA':'untouched'},'conversations':set()} for t in policy['tenants']}
        keys=['a'*64,'b'*64];calls=[];composes=[];exported=[];restarted=set()
        def request(tenant,path,key=None,method='GET',body=None):
            calls.append((tenant['id'],path,method));row=app[tenant['id']]
            if path.startswith('/api/conversations/search'):
                return 200,json.dumps({'items':[{'execution_status':'running'}] if mode=='busy' else [],'next_page_id':None}).encode()
            if path=='/api/settings':return 200,b'{"agent_settings":{}}'
            if method=='PUT':row['secrets'][body['name']]=body['value'];return 200,b'{}'
            if method=='POST':
                self.assertIsNone(body['initial_message']);row['conversations'].add(body['conversation_id']);return 201,b'{}'
            identifier=path.rsplit('/',1)[-1];secret='/settings/secrets/' in path
            if method=='DELETE':
                if secret:row['secrets'].pop(identifier,None)
                else:row['conversations'].discard(identifier)
                return 200,b'{}'
            if restarted and mode in ('leak_peer_secret','leak_peer_conversation') and method=='GET':
                peer=app['probe-b' if tenant['id']=='probe-a' else 'probe-a']
                if mode=='leak_peer_secret' and secret and identifier in peer['secrets']:return 200,peer['secrets'][identifier].encode()
                if mode=='leak_peer_conversation' and not secret and identifier in peer['conversations']:return 200,b'{}'
            if secret:return (200,row['secrets'][identifier].encode()) if identifier in row['secrets'] else (404,b'')
            return (200 if identifier in row['conversations'] else 404),b'{}'
        def compose(engine,tenant,*args):
            composes.append((tenant['id'],args[0]))
            if mode=='partial_stop' and args[0]=='stop':raise P.store.StorageError('partial_stop')
            if args[0]=='start':
                restarted.add(tenant['id']);row=app[tenant['id']]
                if mode=='lost_secret':row['secrets']={'KEEP_REAL_DATA':'untouched'}
                if mode=='corrupt_secret':
                    for name in row['secrets']:
                        if name.startswith('RECOVERY_'):row['secrets'][name]='corrupt'
                if mode=='lost_conversation':row['conversations'].clear()
                if mode in ('lost_marker','corrupt_marker'):
                    for base in paths[tenant['id']][:2]:
                        for path in base.glob('.recovery-probe-*'):
                            if mode=='lost_marker':path.unlink()
                            else:path.write_text('corrupt')
        def key(tenant,name):
            if tenant['id'] in restarted and mode=='changed_'+name:return 'e'*64
            return keys[0 if tenant['id']=='probe-a' else 1] if name=='api-key.txt' else ('c' if tenant['id']=='probe-a' else 'd')*64
        api=types.SimpleNamespace(BASE=self.base,PilotError=P.PilotError,
          store=types.SimpleNamespace(safe_path=mock.Mock(),StorageError=P.store.StorageError),
          health=lambda policy:keys,request=request,key=key,runtime=mock.Mock(),compose=compose,
          paths=lambda tenant:paths[tenant['id']],conversation_payload=P.conversation_payload)
        original_snapshot=R.snapshot;original_read=R.read_snapshot
        def snapshot(*args):
            path,digest=original_snapshot(*args);exported.append(path.read_bytes())
            return path,('0'*64 if mode=='corrupt' else digest)
        with mock.patch.object(R,'snapshot',side_effect=snapshot), \
             mock.patch.object(R,'read_snapshot',side_effect=lambda api,policy,path,digest:original_read(api,policy,path,digest,owner=os.getuid())):
            if mode:
                with self.assertRaises(P.PilotError) as error:R.recovery_check(api,policy,{},mock.Mock())
                result=error.exception
            else:result=R.recovery_check(api,policy,{},mock.Mock())
        self.assertTrue(all(row['secrets']=={'KEEP_REAL_DATA':'untouched'} and not row['conversations'] for row in app.values()))
        if mode=='corrupt_marker':
            # Changed files must be retained rather than deleted by privileged cleanup.
            self.assertTrue(list(self.base.rglob('.recovery-probe-*')))
        else:self.assertFalse(list(self.base.rglob('.recovery-probe-*')))
        for raw in exported:
            self.assertNotIn(keys[0].encode(),raw);self.assertNotIn(keys[1].encode(),raw)
            self.assertNotIn(b'KEEP_REAL_DATA',raw)
        return result,composes,calls
    def test_restart_record_loss_corruption_and_peer_exposure_fail_acceptance(self):
        for mode in ('lost_secret','corrupt_secret','lost_conversation','lost_marker','corrupt_marker','leak_peer_secret','leak_peer_conversation'):
            with self.subTest(mode=mode):
                # Each lifecycle gets independent directories and a clean backend.
                case=RecoveryTests();case.setUp()
                try:
                    result,_,calls=case.exercise(mode)
                    self.assertEqual(str(result),'synthetic_recovery_probe_failed')
                    self.assertEqual(result.details['failed_stage'],'restart_pilots')
                    self.assertEqual(sum(method=='POST' for _,_,method in calls),2)
                    self.assertTrue(result.details['synthetic_manifest_retained'])
                    self.assertEqual(result.details['synthetic_cleanup'],'pending' if mode=='corrupt_marker' else 'completed')
                finally:case.doCleanups()

    def test_both_native_keys_must_survive_restart(self):
        for name in ('api-key.txt','secret-key.txt'):
            with self.subTest(key_role=name):
                case=RecoveryTests();case.setUp()
                try:
                    result,composes,_=case.exercise('changed_'+name)
                    self.assertEqual(str(result),'synthetic_recovery_probe_failed')
                    self.assertEqual(result.details['failed_stage'],'restart_pilots')
                    self.assertNotIn(('probe-b','stop'),composes)
                finally:case.doCleanups()

    def test_success_preserves_native_keys_restores_canaries_and_removes_manifest(self):
        result,composes,calls=self.exercise()
        self.assertEqual(result['status'],'passed');self.assertTrue(result['synthetic_manifest_removed'])
        self.assertEqual(result['household_readiness'],'pending')
        self.assertEqual(composes,[('probe-a','stop'),('probe-a','start'),('probe-b','stop'),('probe-b','start')])
        self.assertEqual(sum(method=='POST' for _,_,method in calls),4)
        self.assertFalse(list(self.base.glob('recovery-*.json')))
    def test_active_work_stops_before_data_or_process_mutation(self):
        result,composes,calls=self.exercise('busy')
        self.assertEqual(str(result),'recovery_requires_idle_bounded_pilots')
        self.assertFalse(composes);self.assertTrue(all(method=='GET' for _,_,method in calls))
    def test_partial_stop_failure_attempts_resume_and_keeps_manifest(self):
        result,composes,_=self.exercise('partial_stop')
        self.assertEqual(str(result),'synthetic_recovery_probe_failed')
        self.assertIn(('probe-a','start'),composes)
        self.assertTrue(list(self.base.glob('recovery-*.json')))
    def test_corrupted_manifest_blocks_import_and_preserves_other_records(self):
        result,_,calls=self.exercise('corrupt')
        self.assertEqual(result.details['failed_stage'],'validate_export')
        self.assertEqual(sum(method=='POST' for _,_,method in calls),2)
        self.assertTrue(list(self.base.glob('recovery-*.json')))


if __name__=='__main__':unittest.main()
