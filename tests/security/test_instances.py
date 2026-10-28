"""Reject isolation drift and prove failure/cleanup behavior without Docker or mounts."""
import copy,contextlib,importlib.util,io,json,os,stat,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('instance_pilot',ROOT/'scripts/instances/instances.py')
P=importlib.util.module_from_spec(spec);sys.modules[spec.name]=P;spec.loader.exec_module(P)

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.policy=P.store.load_policy();self.lock=P.store.read_yaml(ROOT/'infra/openhands/versions.yaml')
        self.tenant=self.policy['tenants'][0];self.config=P.render(self.tenant,self.lock)
    def test_two_distinct_users_mounts_network_projects_and_loopback_ports(self):
        a=self.config;b=P.render(self.policy['tenants'][1],self.lock)
        self.assertNotEqual(a['services']['openhands']['user'],b['services']['openhands']['user'])
        self.assertNotEqual(a['services']['ingress']['ports'],b['services']['ingress']['ports'])
        aset={m['source'] for m in a['services']['openhands']['volumes'] if not m.get('read_only')}
        bset={m['source'] for m in b['services']['openhands']['volumes'] if not m.get('read_only')}
        self.assertFalse(aset&bset)
        self.assertNotEqual(P.project(self.tenant),P.project(self.policy['tenants'][1]))
    def mutate(self,change):
        value=copy.deepcopy(self.config);change(value)
        with self.assertRaises(P.PilotError):P.validate_config(value,self.tenant,self.lock)
    def test_wildcard_port_shared_network_and_extra_service_rejected(self):
        for change in [lambda c:c['services']['ingress'].update(ports=['0.0.0.0:8101:8080']),
                       lambda c:c['services']['openhands'].update(networks=['backend','frontend']),
                       lambda c:c['networks']['backend'].update(internal=False),
                       lambda c:c['services'].update(ollama={})]:self.mutate(change)
    def test_docker_socket_named_or_anonymous_state_and_foreign_mount_rejected(self):
        for change in [lambda c:c['services']['openhands']['volumes'][0].update(source='/var/run/docker.sock'),
                       lambda c:c['services']['openhands']['volumes'][0].update(type='volume'),
                       lambda c:c['services']['openhands']['volumes'].pop(1),
                       lambda c:c['services']['openhands']['volumes'][0].update(source='/other/state'),
                       lambda c:c['services']['openhands']['volumes'][0]['bind'].update(create_host_path=True)]:self.mutate(change)
    def test_root_privilege_gpu_devices_and_unbounded_resources_rejected(self):
        for change in [lambda c:c['services']['openhands'].update(user='0:0'),
                       lambda c:c['services']['openhands'].update(privileged=True),
                       lambda c:c['services']['openhands'].update(devices=['/dev/nvidia0']),
                       lambda c:c['services']['openhands'].update(mem_limit='100g'),
                       lambda c:c['services']['openhands'].update(cap_drop=[])]:self.mutate(change)
    def test_key_injection_shared_master_key_and_telemetry_rejected(self):
        for change in [lambda c:c['services']['openhands']['environment'].update(AGENT_CANVAS_ALLOW_LAN_SESSION_KEY='true'),
                       lambda c:c['services']['openhands']['environment'].update(OH_SECRET_KEY='shared'),
                       lambda c:c['services']['openhands']['environment'].update(OH_TELEMETRY_EXPORTER='posthog'),
                       lambda c:c['services']['openhands']['environment'].update(SESSION_API_KEY='shared')]:self.mutate(change)
    def test_readonly_root_filters_bounded_tmpfs_and_immutable_images_required(self):
        for change in [lambda c:c['services']['openhands'].update(read_only=False),
                       lambda c:c['services']['openhands'].update(security_opt=[]),
                       lambda c:c['services']['openhands'].update(tmpfs=['/tmp:size=100g']),
                       lambda c:c['services']['openhands'].update(image='openhands:latest')]:self.mutate(change)
    def test_unknown_template_input_is_not_expanded_from_host_environment(self):
        template=P.store.read_yaml(P.TEMPLATE);template['services']['openhands']['image']='${SECRET}'
        with self.assertRaises(P.PilotError):P.render(self.tenant,self.lock,template)
    def test_container_accounts_remap_only_openhands_and_reject_collision(self):
        text='root:x:0:0:root:/root:/bin/bash\nopenhands:x:10001:10001::/home/openhands:/bin/bash\n'
        result=P.remap_accounts(text,self.tenant,'passwd')
        self.assertIn('root:x:0:0:',result);self.assertIn('openhands:x:200001:200001:',result)
        for bad in ['root:x:0:0:root:/root:/bin/bash\n',text+'other:x:200001:0::/:/bin/sh\n',text+'invalid\n']:
            with self.assertRaises(P.PilotError):P.remap_accounts(bad,self.tenant,'passwd')

class PreflightTests(unittest.TestCase):
    def setUp(self):self.lock=P.store.read_yaml(ROOT/'infra/openhands/versions.yaml')
    def test_missing_cache_fails_without_downloading_or_running(self):
        engine=mock.Mock();engine.run.return_value=b'[]'
        with self.assertRaises(P.PilotError):P.image_metadata(engine,self.lock)
        self.assertEqual(engine.run.call_count,1)
        self.assertEqual(engine.run.call_args.args[0][3:5],['image','inspect'])
    def test_wrong_entrypoint_fails_and_removes_only_unique_preflight(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if args[3:5]==['image','inspect']:return json.dumps([args[-1]]).encode()
            if args[3]=='run':return json.dumps({'entrypoint':'wrong'}).encode()
            if args[3]=='rm':return b''
            raise AssertionError(args)
        engine=mock.Mock();engine.run.side_effect=run
        with self.assertRaises(P.PilotError):P.image_metadata(engine,self.lock)
        container=next(args for args in calls if args[3]=='run')
        self.assertEqual(container[container.index('--network')+1],'none')
        self.assertNotIn('--mount',container);self.assertNotIn('--volume',container)
        self.assertEqual(calls[-1][-1],container[container.index('--name')+1])
        self.assertTrue(calls[-1][-1].startswith('agent-platform-instance-preflight-'))
    def test_memory_capacity_gate_does_not_assume_missing_value_is_zero_or_pass(self):
        for text in ('MemTotal: 30000000 kB\n','MemAvailable: 1000 kB\n'):
            with mock.patch.object(P.Path,'read_text',return_value=text):
                with self.assertRaises(P.PilotError):P.memory_available()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        ConfigTests.setUp(self);self.engine=mock.Mock();self.ids={'openhands':'a'*64,'ingress':'b'*64}
        self.responses={}
        for name,service in self.config['services'].items():
            self.responses[self.ids[name]]={'running':True,'apparmor':'docker-default','image':service['image'],'user':service['user'],
              'labels':{'com.docker.compose.project':P.project(self.tenant),'com.docker.compose.service':name},
              'mounts':[{'Type':'bind','Source':m['source'],'Destination':m['target'],'RW':not m.get('read_only',False)} for m in service['volumes']],
              'host':{'NetworkMode':P.project(self.tenant)+'_'+service['networks'][0],
                'PidMode':'','IpcMode':'private','UTSMode':'','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true','apparmor=docker-default'],
                'Memory':2*1024**3 if name=='openhands' else 64*1024**2,
                'NanoCpus':2_000_000_000 if name=='openhands' else 500_000_000,'PidsLimit':256 if name=='openhands' else 64,
                'LogConfig':{'Type':'json-file','Config':{'max-size':'2m','max-file':'2'}},
                'Tmpfs':dict(t.split(':',1) for t in service['tmpfs']),
                'PortBindings':{} if name=='openhands' else {'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8101'}]}},
              'networks':{P.project(self.tenant)+'_'+n:{} for n in service['networks']}}
        def run(args,**kwargs):
            if args[3]=='ps':
                name=args[-1].split('=')[-1];return self.ids[name].encode()
            if args[3]=='inspect':return json.dumps(self.responses[args[-1]]).encode()
            if args[3:5]==['network','inspect']:
                return json.dumps([{'Internal':args[-1].endswith('_backend'),'Driver':'bridge'}]).encode()
            raise AssertionError(args)
        self.engine.run.side_effect=run
    def test_expected_live_metadata_passes_and_stopped_instances_can_be_removed(self):
        self.assertEqual(set(P.runtime(self.engine,self.tenant,self.lock)),{'openhands','ingress'})
        for record in self.responses.values():record['running']=False
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
        P.runtime(self.engine,self.tenant,self.lock,running=False)
    def test_shared_host_missing_and_unknown_namespace_modes_are_rejected(self):
        for service in self.ids:
            record=self.responses[self.ids[service]]
            for field in ('PidMode','IpcMode','UTSMode','NetworkMode'):
                original=record['host'][field]
                for value in ('host','container:foreign-instance','unknown',None):
                    with self.subTest(service=service,field=field,value=value):
                        record['host'][field]=value
                        with self.assertRaises(P.PilotError) as error:P.runtime(self.engine,self.tenant,self.lock)
                        self.assertIn('private_namespaces',error.exception.details['failed_checks'])
                del record['host'][field]
                with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
                record['host'][field]=original
            record['host']['IpcMode']='shareable'
            P.runtime(self.engine,self.tenant,self.lock)

    def test_wrong_live_uid_gid_and_missing_identity_are_rejected(self):
        for service in self.ids:
            record=self.responses[self.ids[service]];original=record['user']
            for value in ('0:0','200002:200002','200001:0','',None):
                with self.subTest(service=service,user=value):
                    record['user']=value
                    with self.assertRaises(P.PilotError) as error:P.runtime(self.engine,self.tenant,self.lock)
                    self.assertIn('user_identity',error.exception.details['failed_checks'])
            record['user']=original

    def test_applied_anonymous_volume_extra_network_and_wildcard_port_fail(self):
        record=self.responses[self.ids['openhands']];record['mounts'].append({'Type':'volume'})
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
        record['mounts'].pop();record['networks']['shared_model']={}
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
        del record['networks']['shared_model']
        self.responses[self.ids['ingress']]['host']['PortBindings']['8080/tcp'][0]['HostIp']='0.0.0.0'
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
    def test_actual_compose_colon_security_syntax_matches_equals_runtime_form(self):
        for record in self.responses.values():
            record['host']['SecurityOpt']=['no-new-privileges:true','apparmor:docker-default']
        P.runtime(self.engine,self.tenant,self.lock)
        for record in self.responses.values():
            record['host']['SecurityOpt']=['no-new-privileges=true','apparmor=docker-default']
        P.runtime(self.engine,self.tenant,self.lock)
        for record in self.responses.values():
            record['host']['SecurityOpt']=['no-new-privileges','apparmor=docker-default']
        P.runtime(self.engine,self.tenant,self.lock)

    def test_disabled_duplicate_unconfined_and_missing_security_controls_fail(self):
        record=self.responses[self.ids['openhands']]
        for options in [[],['no-new-privileges:false','apparmor:docker-default'],
          ['no-new-privileges:true','apparmor:unconfined'],
          ['no-new-privileges:true','apparmor:docker-default','seccomp=unconfined'],
          ['no-new-privileges:true','apparmor:docker-default','no-new-privileges:false']]:
            record['host']['SecurityOpt']=options
            with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
        record['host']['SecurityOpt']=['no-new-privileges:true','apparmor:docker-default']
        record['apparmor']=''
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)

    def test_failure_reports_fixed_control_names_without_inspect_values(self):
        record=self.responses[self.ids['openhands']];record['host']['Memory']=0
        record['host']['private_canary']='DO_NOT_EXPOSE_THIS_VALUE'
        with self.assertRaises(P.PilotError) as error:P.runtime(self.engine,self.tenant,self.lock)
        self.assertEqual(error.exception.details,{'tenant':'probe-a','service':'openhands','failed_checks':['memory_limit']})
        self.assertNotIn('DO_NOT_EXPOSE_THIS_VALUE',str(error.exception.details))

    def test_stopped_diagnostic_is_read_only_and_does_not_claim_running_pass(self):
        for record in self.responses.values():
            record['running']=False
            record['host']['SecurityOpt']=['no-new-privileges:true','apparmor:docker-default']
        with mock.patch.object(P,'selected',side_effect=lambda engine,tenant,service,required=False:self.ids[service]):
            result=P.diagnose(self.policy,self.lock,self.engine)
        self.assertEqual(result['status'],'collected')
        self.assertTrue(all(item['state']=='not_running' for item in result['instances']))
        self.assertTrue(all('running' not in item['process_checks'] for item in result['instances']))
        self.assertEqual(result['household_readiness'],'pending')
        self.assertTrue(all(args.args[0][3] in ('inspect','network') for args in self.engine.run.call_args_list))

    def test_missing_required_storage_aborts_before_any_docker_operation(self):
        with mock.patch.object(P.store,'check',side_effect=P.store.StorageError('required_mount_missing')):
            with self.assertRaises(P.store.StorageError):P.operate('up',self.policy,self.lock,self.engine)
        self.engine.run.assert_not_called()
    def test_foreign_process_image_and_resource_drift_fail(self):
        record=self.responses[self.ids['openhands']]
        for field,value in [('ReadonlyRootfs',False),('Privileged',True),('Devices',[{}]),('Memory',0)]:
            before=record['host'].get(field);record['host'][field]=value
            with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)
            record['host'][field]=before
        record['labels']['com.docker.compose.project']='foreign'
        with self.assertRaises(P.PilotError):P.runtime(self.engine,self.tenant,self.lock)

    def test_failed_second_start_stops_only_both_synthetic_projects(self):
        calls=[]
        def compose(engine,tenant,*args):
            calls.append((P.project(tenant),args))
            if args[0]=='up' and tenant['id']=='probe-b':raise P.store.StorageError('operation_failed')
        with mock.patch.object(P.store,'check'),mock.patch.object(P,'memory_available',return_value=10), \
             mock.patch.object(P,'image_metadata'),mock.patch.object(P,'controls'), \
             mock.patch.object(P,'selected',return_value=None),mock.patch.object(P.socket,'socket'), \
             mock.patch.object(P,'compose',side_effect=compose):
            with self.assertRaises(P.store.StorageError) as error:P.operate('up',self.policy,self.lock,self.engine)
        self.assertEqual(error.exception.recovery,{'probe-a':'stop_completed','probe-b':'stop_completed'})
        stopped=[name for name,args in calls if args==('stop',)]
        self.assertEqual(set(stopped),{'agent-platform-probe-a','agent-platform-probe-b'})
        self.assertNotIn('agent-platform-local',stopped)

    def test_recovery_stop_failure_is_reported_without_replacing_original_error(self):
        def compose(engine,tenant,*args):
            if args[0]=='up' and tenant['id']=='probe-b':raise P.store.StorageError('original_start_failure')
            if args[0]=='stop' and tenant['id']=='probe-b':raise P.store.StorageError('stop_failure')
        with mock.patch.object(P.store,'check'),mock.patch.object(P,'memory_available',return_value=10), \
             mock.patch.object(P,'image_metadata'),mock.patch.object(P,'controls'), \
             mock.patch.object(P,'selected',return_value=None),mock.patch.object(P.socket,'socket'), \
             mock.patch.object(P,'compose',side_effect=compose):
            with self.assertRaises(P.store.StorageError) as error:P.operate('up',self.policy,self.lock,self.engine)
        self.assertEqual(str(error.exception),'original_start_failure')
        self.assertEqual(error.exception.recovery,{'probe-a':'stop_completed','probe-b':'stop_failed'})

    def test_low_memory_aborts_before_any_docker_start(self):
        with mock.patch.object(P.store,'check'),mock.patch.object(P,'memory_available',side_effect=P.PilotError('less_than_6_gib_available_memory')):
            with self.assertRaises(P.PilotError):P.operate('up',self.policy,self.lock,self.engine)
        self.engine.run.assert_not_called()


class KeyAndAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.policy=P.store.load_policy();self.lock=P.store.read_yaml(ROOT/'infra/openhands/versions.yaml')
    def test_native_key_reader_refuses_symlinks_hardlinks_and_public_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);home=state/'.openhands';home.mkdir(mode=0o700)
            canvas=home/'agent-canvas';canvas.mkdir(mode=0o700)
            p=canvas/'api-key.txt';p.write_text('a'*64);p.chmod(0o600)
            tenant={'uid':os.getuid(),'gid':os.getgid(),'id':'probe-a'}
            with mock.patch.object(P,'paths',return_value=(state,state,state)):
                self.assertEqual(P.key(tenant,'api-key.txt'),'a'*64)
                p.chmod(0o644)
                with self.assertRaises(P.PilotError):P.key(tenant,'api-key.txt')
                p.chmod(0o600);alias=canvas/'alias';alias.hardlink_to(p)
                with self.assertRaises(P.PilotError):P.key(tenant,'api-key.txt')
                alias.unlink();p.unlink();p.symlink_to('/etc/passwd')
                with self.assertRaises(OSError):P.key(tenant,'api-key.txt')
    def test_native_directory_links_cannot_redirect_privileged_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'.openhands').symlink_to('/tmp')
            with mock.patch.object(P,'paths',return_value=(state,state,state)):
                with self.assertRaises(OSError):P.key(self.policy['tenants'][0],'api-key.txt')
    def test_shared_session_or_encryption_keys_fail_health(self):
        with mock.patch.object(P,'key',return_value='a'*64),mock.patch.object(P,'request',return_value=(200,b'{"agent_settings":{}}')):
            with self.assertRaisesRegex(P.PilotError,'native_keys_not_distinct'):P.health(self.policy)
    def test_html_success_does_not_count_as_authenticated_backend_health(self):
        with mock.patch.object(P,'key',return_value='a'*64),mock.patch.object(P,'request',return_value=(200,b'<html>UI</html>')):
            with self.assertRaisesRegex(P.PilotError,'unexpected_settings_response'):P.health(self.policy)
    def test_redirects_are_never_followed_with_a_key(self):
        self.assertIsNone(P.NoRedirect().redirect_request(None,None,302,'redirect',{},'http://other'))
    def test_route_rejects_non_api_and_traversal_before_network(self):
        for path in ['http://other','/api/../../secret','/canvas']:
            with self.assertRaises(P.PilotError):P.request(self.policy['tenants'][0],path,'private')
    def run_acceptance(self,fail=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        paths={t['id']:(Path(temp.name)/t['id']/'state',Path(temp.name)/t['id']/'workspace',Path(temp.name)/t['id']/'control') for t in self.policy['tenants']}
        for selected in paths.values():
            for path in selected:path.mkdir(parents=True)
        secrets_store={t['id']:{} for t in self.policy['tenants']};calls=[]
        keys=['a'*64,'b'*64];conversations={t['id']:set() for t in self.policy['tenants']}
        def request(tenant,path,credential=None,method='GET',body=None):
            calls.append((tenant['id'],path,method))
            index=0 if tenant['id']=='probe-a' else 1
            if credential!=keys[index]:return (200 if fail=='cross_key' and credential else 401),b''
            if path.startswith('/api/conversations'):
                records=conversations[tenant['id']];identifier=path.rsplit('/',1)[-1]
                if method=='POST':
                    self.assertIsNone(body['initial_message']);self.assertNotIn('run',body)
                    records.add(body['conversation_id']);return 201,b'{}'
                if method=='DELETE':records.discard(identifier);return 200,b'{}'
                if fail=='conversation_read' and identifier in records:return 500,b'private details'
                return (200 if identifier in records else 404),b'{}'
            if method=='PUT':
                secrets_store[tenant['id']][body['name']]=body['value'];return 200,b'{}'
            name=path.rsplit('/',1)[-1];store=secrets_store[tenant['id']]
            if method=='DELETE':store.pop(name,None);return 200,b'{}'
            if fail=='secret_read' and name in store:return 500,b'private error details'
            if name in store:return 200,store[name].encode()
            return 404,b''
        engine=mock.Mock();engine.run.return_value=json.dumps({k:True for k in ('uid_matches','own_state_visible','own_workspace_visible','foreign_host_path_denied')}).encode()
        with mock.patch.object(P.store,'check'),mock.patch.object(P,'runtime'),mock.patch.object(P,'health',return_value=keys), \
             mock.patch.object(P,'selected',return_value='a'*64),mock.patch.object(P,'request',side_effect=request), \
             mock.patch.object(P,'paths',side_effect=lambda t:paths[t['id']]),mock.patch.object(P.os,'fchown'):
            if fail:
                with self.assertRaises(P.PilotError):P.acceptance(self.policy,self.lock,engine)
                result=None
            else:result=P.acceptance(self.policy,self.lock,engine)
        self.assertTrue(all(not store for store in secrets_store.values()))
        self.assertTrue(all(not records for records in conversations.values()))
        self.assertFalse(list(Path(temp.name).rglob('.instance-canary-*')))
        return result,calls
    def test_both_tenants_probe_own_and_foreign_secret_stores_and_cleanup(self):
        result,calls=self.run_acceptance()
        self.assertEqual(result['status'],'passed');self.assertEqual(len(result['instances']),2)
        self.assertEqual(result['household_readiness'],'pending')
        self.assertEqual(sum(method=='PUT' for _,_,method in calls),2)
        self.assertEqual(sum(method=='POST' for _,_,method in calls),2)
    def test_cross_key_acceptance_cannot_pass_and_cleans_canaries(self):self.run_acceptance('cross_key')
    def test_conversation_failure_cleans_its_idle_record_and_files(self):self.run_acceptance('conversation_read')
    def test_secret_read_failure_deletes_only_its_created_canary(self):self.run_acceptance('secret_read')

if __name__=='__main__':unittest.main()
