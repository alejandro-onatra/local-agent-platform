"""Named-user scope, blueprint graph, storage separation and no direct bypass."""
import datetime,os,stat,contextlib,copy,importlib.util,ipaddress,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('household_tests',ROOT/'scripts/household/household.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)

class HouseholdTests(unittest.TestCase):
    def test_named_policy_and_real_storage_are_separate_from_synthetic(self):
        gateway,pilot,store=H.source()
        self.assertEqual([t['id'] for t in H.POLICY['tenants']],['alejandro','kimberly'])
        self.assertEqual(H.storage_policy()['purpose'],'household_user_instances')
        self.assertNotIn('https_port',H.storage_policy()['tenants'][0])
        self.assertEqual(H.POLICY['volumes_mib'],{'workspace':2048,'state':512})
        a,b=H.POLICY['tenants']
        self.assertNotEqual(H.paths(a)[0],H.paths(b)[0]);self.assertNotEqual(a['uid'],b['uid'])
        self.assertNotIn('pilot',str(H.BASE))

    def test_blueprint_enforces_distinct_apps_groups_and_totp_without_global_default(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        data=source.parse(H.blueprint('192.168.42.20'))
        entries={row['id']:row for row in data['entries']}
        self.assertNotIn('outpost',entries);self.assertFalse(entries['brand']['attrs']['default'])
        self.assertEqual(entries['brand']['identifiers']['domain'],'192.168.42.20:8443')
        self.assertEqual(entries['mfa-login']['attrs']['device_classes'],['totp'])
        self.assertEqual(entries['mfa-login']['attrs']['not_configured_action'],'configure')
        self.assertEqual(entries['mfa-access']['attrs']['not_configured_action'],'deny')
        self.assertEqual(entries['mfa-login']['attrs']['configuration_stages'],[source.Ref('totp')])
        self.assertIsNone(entries['identify']['attrs']['enrollment_flow'])
        for user,port in [('alejandro',8444),('kimberly',8445)]:
            self.assertEqual(entries['provider-'+user]['attrs']['external_host'],f'https://192.168.42.20:{port}')
            self.assertEqual(entries['provider-'+user]['attrs']['mode'],'forward_single')
            self.assertFalse(entries['group-'+user]['attrs']['is_superuser'])
            self.assertEqual(entries['allow-'+user]['identifiers']['group'],source.Ref('group-'+user))
        with self.assertRaises(ValueError):H.blueprint('192.168.42.20\nmalicious')

    def test_instances_have_no_host_ports_distinct_mounts_and_local_model_relay(self):
        gateway,pilot,store=H.source();lock=store.read_yaml(ROOT/'infra/openhands/versions.yaml')
        configurations=[H.render(t,lock) for t in H.POLICY['tenants']]
        for tenant,config in zip(H.POLICY['tenants'],configurations):
            for name,service in config['services'].items():
                self.assertNotIn('ports',service)
                self.assertTrue(service['read_only']);self.assertEqual(service['cap_drop'],['ALL'])
                self.assertIn('no-new-privileges:true',service['security_opt'])
            agent=config['services']['openhands']
            self.assertEqual(agent['networks'],['backend'])
            self.assertEqual(agent['user'],f"{tenant['uid']}:{tenant['uid']}")
            self.assertEqual(agent['environment']['AGENT_CANVAS_ALLOW_LAN_SESSION_KEY'],'true')
            self.assertTrue(config['networks']['backend']['internal'])
            self.assertEqual(config['services']['model-relay']['networks'],['backend','models'])
            self.assertEqual(config['networks']['models']['name'],'agent-platform-local_default')
            self.assertTrue(all('pilot' not in item['source'] for item in agent['volumes'] if 'source' in item and '/var/lib' in item['source']))
        self.assertNotEqual(configurations[0]['services']['openhands']['volumes'][0]['source'],configurations[1]['services']['openhands']['volumes'][0]['source'])

    def test_caddy_checks_auth_and_exact_user_before_each_upstream(self):
        text=(ROOT/'infra/gateway/Caddyfile').read_text()
        for user,port in [('alejandro',8444),('kimberly',8445)]:
            block=text.split('https://__ADDRESS__:'+str(port)+' {',1)[1]
            if user=='alejandro':block=block.split('https://__ADDRESS__:8445',1)[0]
            self.assertLess(block.index('request_header -X-Authentik-*'),block.index('forward_auth'))
            self.assertLess(block.index('forward_auth'),block.index('respond @wrong_user 403'))
            self.assertLess(block.index('respond @wrong_user 403'),block.index('reverse_proxy agent-platform-household-'+user))
            self.assertIn('not header X-Authentik-Username '+user,block)
            self.assertIn('Cache-Control no-store',block);self.assertIn('stream_timeout 5m',block)

    def test_privileged_ipc_keeps_passwords_off_arguments_and_sanitizes_failures(self):
        @contextlib.contextmanager
        def memory_file():
            with io.BytesIO() as value:yield value
        for raw_error,expected in [('household_identity_operation_failed_blueprint_validation','household_identity_operation_failed_blueprint_validation'),
                                   ('secret VALUE must never appear','household_privileged_operation_failed')]:
            def command(args,data,result,**kwargs):
                self.assertNotIn('synthetic-password',repr(args))
                self.assertIn(b'synthetic-password',data.read())
                result.write(json.dumps({'status':'failed','error':raw_error}).encode())
                raise RuntimeError('private native output')
            helper=types.SimpleNamespace(memory_file=memory_file,stream_command=command,BackupError=RuntimeError)
            gateway=types.SimpleNamespace(pki=lambda:types.SimpleNamespace(backup=lambda:helper))
            with mock.patch.object(H,'helpers',return_value=(gateway,None,None)):
                with self.assertRaises(H.HouseholdError) as error:H.root_call('root-setup',{'password':'synthetic-password'})
                self.assertEqual(str(error.exception),expected)

    def test_general_storage_record_retains_the_purpose_boundary(self):
        _,_,store=H.helpers()
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);policy=H.storage_policy()
            (base/'record.yaml').write_text('schema_version: 1\npurpose: synthetic_storage_probe\npolicy_sha256: '+store.policy_hash(policy)+'\n')
            (base/'record.yaml').chmod(0o600)
            with mock.patch.object(store,'safe_path'):
                # Wrong-purpose records cannot adopt or reinterpret the synthetic pilot.
                with self.assertRaises(store.StorageError):store.inspect_record(policy,base)

class InvitationTests(unittest.TestCase):
    def policy(self, user='kimberly', mutate=None):
        now=datetime.datetime(2026,10,26,tzinfo=datetime.timezone.utc)
        invite=types.SimpleNamespace(name='family-invite-'+user,single_use=True,expiring=True,
            expires=now+datetime.timedelta(hours=24),flow=types.SimpleNamespace(slug='family-enroll-'+user,pk=__import__('uuid').UUID('11111111-1111-1111-1111-111111111111')),
            fixed_data={'generation':'a'*64},pk=None)
        group=types.SimpleNamespace(is_superuser=False,attributes={'invitation_generation':'a'*64})
        plan=types.SimpleNamespace(flow_pk=invite.flow.pk.hex,context={'invitation':invite,'invitation_in_effect':True,
                                           'groups':['attacker-admin-group'],'prompt_data':{'is_superuser':True}})
        data={'password':'synthetic long passphrase only','password_repeat':'synthetic long passphrase only',
              'username':'alejandro' if user=='kimberly' else 'kimberly',
              'is_superuser':True,'attributes':{'admin':True},'groups':['admin']}
        existing=types.SimpleNamespace(exists=lambda:False)
        users=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kw:existing))
        class User:
            objects=users.objects
            def __init__(self,**kw):self.__dict__.update(kw)
        groups=types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda **kw:group))
        request=types.SimpleNamespace(context={'prompt_data':data},http_request=types.SimpleNamespace(
            session={'authentik/flows/plan':plan},resolver_match=types.SimpleNamespace(kwargs={'flow_slug':'family-enroll-'+user})))
        self.policy_request=request
        validation=mock.Mock()
        if mutate:mutate(invite,group,plan,data,existing,validation)
        modules={
            'django.utils.timezone':types.SimpleNamespace(now=lambda:now),
            'django.contrib.auth.password_validation':types.SimpleNamespace(validate_password=validation),
            'authentik.core.models':types.SimpleNamespace(User=User,Group=groups),
            'authentik.flows.views.executor':types.SimpleNamespace(SESSION_KEY_PLAN='authentik/flows/plan')}
        expression=(ROOT/'scripts/household/invitation-policy.expression').read_text().replace('__USER__',user).replace(
            '__APPLICATION_URL__',f"https://192.168.42.20:{8444 if user=='alejandro' else 8445}/canvas")
        messages=[]
        self.last_policy_messages=messages
        namespace={'request':request,'ak_message':messages.append}
        with mock.patch.dict(sys.modules,modules):
            exec('def evaluate():\n'+''.join('    '+line+'\n' for line in expression.splitlines()),namespace)
            passed=namespace['evaluate']()
        return passed,plan,data

    def test_identity_is_rebuilt_and_privilege_inputs_discarded_for_both_users(self):
        for user in ('alejandro','kimberly'):
            passed,plan,data=self.policy(user)
            self.assertTrue(passed)
            self.assertEqual(set(data),{'username','name','password','attributes'})
            self.assertEqual(data['username'],user)
            self.assertEqual(data['attributes'],{'agent_platform_managed':'household-v1'})
            self.assertEqual(plan.context['prompt_data'],{})
            self.assertNotIn('groups',plan.context)

    def test_missing_invitation_and_missing_invitation_effect_are_denied(self):
        for key in ('invitation','invitation_in_effect'):
            self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:p.context.pop(key))[0])

    def test_expired_invitation_and_expiry_boundary_are_denied(self):
        for seconds in (0,-1):
            self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:setattr(i,'expires',
                datetime.datetime(2026,10,26,tzinfo=datetime.timezone.utc)+datetime.timedelta(seconds=seconds)))[0])

    def test_other_user_flow_other_name_multiuse_and_nonexpiring_are_denied(self):
        mutations=[lambda i:setattr(i.flow,'slug','family-enroll-alejandro'),
                   lambda i:setattr(i,'name','family-invite-alejandro'),
                   lambda i:setattr(i,'single_use',False),lambda i:setattr(i,'expiring',False),
                   lambda i:setattr(i,'expires',None)]
        for mutation in mutations:
            self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:mutation(i))[0])

    def test_revocation_generation_invalidates_in_progress_password_form(self):
        self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:g.attributes.update(invitation_generation='replaced'))[0])

    def test_missing_generation_is_not_a_valid_invitation(self):
        def mutate(i,g,p,d,e,v):i.fixed_data.clear();g.attributes.clear()
        self.assertFalse(self.policy(mutate=mutate)[0])

    def test_admin_group_and_existing_account_cannot_be_enrolled(self):
        self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:setattr(g,'is_superuser',True))[0])
        self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:setattr(e,'exists',lambda:True))[0])

    def test_short_mismatched_or_native_rejected_password_is_denied(self):
        mutations=[lambda d,v:d.update(password='short',password_repeat='short'),
                   lambda d,v:d.update(password_repeat='different value'),
                   lambda d,v:setattr(v,'side_effect',ValueError('password rejected'))]
        for mutation in mutations:
            self.assertFalse(self.policy(mutate=lambda i,g,p,d,e,v:mutation(d,v))[0])

    def test_enrollment_graph_has_no_public_signup_and_totp_before_session(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        entries={row['id']:row for row in source.parse(H.blueprint('192.168.42.20'))['entries']}
        for user in ('alejandro','kimberly'):
            self.assertEqual(entries['enroll-'+user]['attrs']['authentication'],'require_unauthenticated')
            self.assertFalse(entries['invite-'+user]['attrs']['continue_flow_without_invitation'])
            self.assertEqual(entries['invite-write-'+user]['attrs']['user_creation_mode'],'always_create')
            self.assertEqual(entries['invite-write-'+user]['attrs']['create_users_group'],source.Ref('group-'+user))
            bindings=sorted([row for row in entries.values() if row['model']=='authentik_flows.flowstagebinding'
                and row['identifiers']['target']==source.Ref('enroll-'+user)],key=lambda row:row['identifiers']['order'])
            self.assertEqual([row['identifiers']['stage'] for row in bindings],
                [source.Ref(key) for key in ('invite-'+user,'invite-credentials-'+user,'invite-write-'+user,'totp','session')])
            self.assertTrue(all(not row['attrs']['evaluate_on_plan'] for row in bindings))
            self.assertEqual(entries['invite-credentials-'+user]['attrs']['validation_policies'],[source.Ref('invite-policy-'+user)])

    def test_private_file_is_exclusive_owner_only_and_result_has_no_bearer(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/'invitations'
            payload={'expires':'2026-10-27T00:00:00+00:00','invitation_url':'https://example.invalid/?itoken=synthetic'}
            result=H.save_invitation('kimberly',payload,directory)
            path=Path(result['private_invitation_file'])
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertIn(payload['invitation_url'],path.read_text())
            self.assertNotIn('itoken',json.dumps(result))
            second=H.save_invitation('kimberly',payload,directory)
            self.assertNotEqual(second['private_invitation_file'],str(path))

    def test_shared_or_symlink_directory_refused_before_credential_write(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/'shared';directory.mkdir(mode=0o755);directory.chmod(0o755)
            with self.assertRaises(H.HouseholdError):H.save_invitation('kimberly',{},directory)
            link=Path(folder)/'link';link.symlink_to(directory,target_is_directory=True)
            with self.assertRaises(H.HouseholdError):H.save_invitation('kimberly',{},link)
            self.assertEqual(list(directory.iterdir()),[])

    def test_setup_sends_no_password_or_user_creation_payload(self):
        calls=[]
        gateway=types.SimpleNamespace(state=lambda:(None,{'address':'192.168.42.20'}))
        def root_call(action,payload):calls.append((action,payload));return {'status':'passed'}
        with mock.patch.object(H,'source',return_value=(gateway,None,None)),mock.patch.object(H,'root_call',side_effect=root_call):
            H.owner_setup()
        self.assertEqual([action for action,_ in calls],['root-status','root-setup'])
        self.assertNotIn('passwords',calls[-1][1])
        self.assertNotIn('password',calls[-1][1])

    def test_unreserved_user_refused_before_privileged_operation(self):
        with mock.patch.object(H,'root_call') as call:
            with self.assertRaises(H.HouseholdError):H.owner_invitation('akadmin')
            call.assert_not_called()

class NativeInvitationOperationTests(unittest.TestCase):
    """Execute the actual issuer function with an isolated ORM boundary.

    This validates our operations, not Authentik's ORM or browser implementation.
    """
    def setUp(self):
        import ast
        source=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='execute')
        helper=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='invitation_entry_url')
        namespace={};exec(compile(ast.Module(body=[helper,function],type_ignores=[]),'native-issuer-test','exec'),namespace)
        self.execute=namespace['execute'];self.rows=[];self.exists=False;self.now=datetime.datetime(2026,10,26,tzinfo=datetime.timezone.utc)
        self.group=types.SimpleNamespace(is_superuser=False,attributes={},save=lambda:None)
        self.admin=types.SimpleNamespace(username='akadmin',is_superuser=True)
        class Groups:
            def select_for_update(inner):return inner
            def get(inner,**kwargs):return self.group
        class Users:
            def filter(inner,**kwargs):return types.SimpleNamespace(exists=lambda:self.exists)
            def get(inner,**kwargs):
                assert kwargs=={'username':'akadmin','is_active':True}
                return self.admin
        class Invitations:
            def including_expired(inner):return inner
            def filter(inner,**kwargs):
                def delete():self.rows[:]=[row for row in self.rows if row.name!=kwargs['name']]
                return types.SimpleNamespace(delete=delete)
            def create(inner,**kwargs):
                import uuid
                row=types.SimpleNamespace(pk=uuid.uuid4(),**kwargs);self.rows.append(row);return row
        @contextlib.contextmanager
        def atomic():
            snapshot=(copy.deepcopy(self.group.attributes),list(self.rows))
            try:yield
            except Exception:
                self.group.attributes,self.rows=snapshot
                raise
        self.modules={
            'authentik.root.setup':types.SimpleNamespace(setup=lambda:None),
            'django':types.SimpleNamespace(setup=lambda:None),
            'authentik.tenants.models':types.SimpleNamespace(Tenant=types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda **kw:contextlib.nullcontext()))),
            'authentik.core.models':types.SimpleNamespace(User=types.SimpleNamespace(objects=Users()),Group=types.SimpleNamespace(objects=Groups()),Application=object),
            'authentik.providers.proxy.models':types.SimpleNamespace(ProxyProvider=object),
            'authentik.outposts.models':types.SimpleNamespace(Outpost=object),
            'django.db':types.SimpleNamespace(transaction=types.SimpleNamespace(atomic=atomic)),
            'authentik.flows.models':types.SimpleNamespace(Flow=types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda **kw:types.SimpleNamespace(slug=kw['slug']))),FlowStageBinding=object),
            'authentik.stages.invitation.models':types.SimpleNamespace(Invitation=types.SimpleNamespace(objects=Invitations()),InvitationStage=object),
            'authentik.stages.prompt.models':types.SimpleNamespace(PromptStage=object),
            'authentik.stages.user_write.models':types.SimpleNamespace(UserWriteStage=object),
            'django.utils.timezone':types.SimpleNamespace(now=lambda:self.now)}

    def run_operation(self,action='invite',name='kimberly'):
        with mock.patch.dict(sys.modules,self.modules):
            return self.execute({'action':action,'username':name,'login_url':'https://192.168.42.20:8443'})

    def test_native_issue_is_one_use_expiring_bound_to_personal_flow(self):
        result=self.run_operation();self.assertEqual(len(self.rows),1);row=self.rows[0]
        self.assertTrue(row.single_use);self.assertTrue(row.expiring)
        self.assertEqual(row.expires,self.now+datetime.timedelta(hours=24))
        self.assertEqual(row.flow.slug,'family-enroll-kimberly')
        self.assertEqual(row.fixed_data['generation'],self.group.attributes['invitation_generation'])
        self.assertIs(row.created_by,self.admin)
        from urllib.parse import urlsplit,parse_qs
        entry=urlsplit(result['invitation_url'])
        self.assertEqual(entry.path,'/flows/-/cancel/')
        target=parse_qs(entry.query,strict_parsing=True)['next'][0]
        route=urlsplit(target)
        self.assertEqual(route.netloc,'');self.assertEqual(route.path,'/if/flow/family-enroll-kimberly/')
        self.assertEqual(parse_qs(route.query),{'itoken':[str(row.pk)]})
        self.assertNotIn('password',result)

    def test_invitation_creator_must_still_have_native_admin_membership(self):
        self.admin.is_superuser=False
        with self.assertRaises(AssertionError):self.run_operation()
        self.assertEqual(self.rows,[])
        self.assertEqual(self.group.attributes,{})

    def test_reissue_replaces_pending_invitation_and_generation(self):
        first=self.run_operation();generation=self.group.attributes['invitation_generation']
        second=self.run_operation()
        self.assertEqual(len(self.rows),1)
        self.assertNotEqual(first['invitation_url'],second['invitation_url'])
        self.assertNotEqual(generation,self.group.attributes['invitation_generation'])

    def test_revoke_does_not_reset_existing_account(self):
        self.run_operation();generation=self.group.attributes['invitation_generation'];self.exists=True
        result=self.run_operation('invite-revoke')
        self.assertEqual(self.rows,[]);self.assertEqual(result['existing_account'],'preserved')
        self.assertNotEqual(generation,self.group.attributes['invitation_generation'])
        self.assertNotIn('invitation_url',result)

    def test_existing_account_issue_rolls_back_without_reset(self):
        self.run_operation();before=(self.rows[0].pk,dict(self.group.attributes));self.exists=True
        with self.assertRaises(AssertionError):self.run_operation()
        self.assertEqual(self.rows[0].pk,before[0]);self.assertEqual(self.group.attributes,before[1])

class EmbeddedOutpostConfigTests(unittest.TestCase):
    def setUp(self):
        import ast,dataclasses
        source=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='configure_embedded_outpost')
        namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'outpost-config-test','exec'),namespace)
        self.configure=namespace['configure_embedded_outpost']
        @dataclasses.dataclass
        class Config:
            authentik_host:str='http://previous.invalid'
            authentik_host_browser:str='https://previous.invalid'
            log_level:str='warning'
            refresh_interval:str='minutes=7'
            docker_labels:dict=dataclasses.field(default_factory=lambda:{'retained':'yes'})
        class Outpost:
            def __init__(inner):
                inner.stored=dataclasses.asdict(Config());inner.ids={'existing-provider'};inner.saves=0
                inner.providers=types.SimpleNamespace(add=lambda *items:inner.ids.update(item.pk for item in items),
                    values_list=lambda *args,**kwargs:list(inner.ids))
            @property
            def config(inner):return Config(**copy.deepcopy(inner.stored))
            @config.setter
            def config(inner,value):inner.stored=dataclasses.asdict(value)
            def save(inner):inner.saves+=1
            def refresh_from_db(inner):pass
        self.outpost=Outpost()
        self.providers=[types.SimpleNamespace(pk='alejandro-provider'),types.SimpleNamespace(pk='kimberly-provider')]

    def test_legacy_dictionary_conversion_reproduces_the_failure(self):
        with self.assertRaises(TypeError):dict(self.outpost.config or {})

    def test_typed_update_preserves_options_existing_providers_and_new_routes(self):
        before=self.outpost.config
        self.configure(self.outpost,self.providers,'https://192.168.42.20:8443')
        after=self.outpost.config
        self.assertEqual(after.authentik_host,'https://192.168.42.20:8443')
        self.assertEqual(after.authentik_host_browser,'https://192.168.42.20:8443')
        self.assertEqual(after.log_level,before.log_level)
        self.assertEqual(after.refresh_interval,before.refresh_interval)
        self.assertEqual(after.docker_labels,before.docker_labels)
        self.assertEqual(self.outpost.ids,{'existing-provider','alejandro-provider','kimberly-provider'})
        self.assertEqual(self.outpost.saves,1)

    def test_repeat_setup_retains_all_providers_without_duplicates(self):
        for _ in range(2):self.configure(self.outpost,self.providers,'https://192.168.42.20:8443')
        self.assertEqual(len(self.outpost.ids),3)

    def test_persisted_readback_mismatch_is_rejected(self):
        self.outpost.refresh_from_db=lambda:self.outpost.stored.update(authentik_host_browser='https://wrong.invalid')
        with self.assertRaises(AssertionError):self.configure(self.outpost,self.providers,'https://192.168.42.20:8443')

class HouseholdDiagnosticTests(unittest.TestCase):
    def test_engine_errors_are_distinguished_without_disclosing_native_values(self):
        for original,category in [('operation_unavailable_or_timed_out','unavailable_or_timed_out'),
                                  ('operation_failed','exec_failed'),('invalid_operation_output','output_too_large'),
                                  ('private-native-key-or-password','transport_failed')]:
            engine=types.SimpleNamespace(run=mock.Mock(side_effect=RuntimeError(original)))
            with self.assertRaises(H.HouseholdError) as error:H.identity(engine,{'action':'status'})
            self.assertEqual(str(error.exception),'household_identity_'+category)
            self.assertNotIn('private-native',str(error.exception))

    def test_native_failed_stage_and_kind_are_preserved_only_from_allowlists(self):
        for payload,expected in [
            ({'status':'failed','stage':'embedded_outpost_save','exception_category':'database_error'},
             'household_identity_operation_failed_embedded_outpost_save_database_error'),
            ({'status':'failed','stage':'private-key','exception_category':'private-value'},
             'household_identity_operation_failed_unknown'),
            ({'status':'failed','stage':[],'exception_category':{}},'household_identity_operation_failed_unknown')]:
            engine=types.SimpleNamespace(run=lambda *args,**kwargs:json.dumps(payload).encode())
            with self.assertRaises(H.HouseholdError) as error:H.identity(engine,{})
            self.assertEqual(str(error.exception),expected)

    def test_invalid_native_responses_have_fixed_errors(self):
        for value,expected in [(b'private logging before JSON','invalid_json_response'),
                               (b'[]','invalid_response_schema'),(b'{"status":"unexpected"}','invalid_response_schema')]:
            engine=types.SimpleNamespace(run=lambda *args,**kwargs:value)
            with self.assertRaises(H.HouseholdError) as error:H.identity(engine,{})
            self.assertEqual(str(error.exception),'household_identity_'+expected)

    def test_read_only_diagnostic_uses_inspect_and_native_diagnose_not_apply(self):
        seen=[]
        def run(args,**kwargs):
            seen.append(args)
            return json.dumps({'Running':True,'OOMKilled':False,'Status':'running','ExitCode':0,
                               'Error':'PRIVATE RAW VALUE NOT TO RETURN'}).encode()
        engine=types.SimpleNamespace(run=run)
        store=types.SimpleNamespace(Engine=lambda:engine)
        def native(engine,payload):
            self.assertEqual(payload,{'action':'diagnose'})
            return {'status':'passed','outpost_exists':True}
        with mock.patch.object(H.os,'geteuid',return_value=0),mock.patch.object(H,'source',return_value=(None,None,store)),mock.patch.object(H,'identity',side_effect=native):
            result=H.diagnose_root()
        self.assertEqual(len(seen),9)
        self.assertTrue(all(args[3]=='inspect' for args in seen))
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertTrue(result['identity']['outpost_exists'])

    def test_diagnostic_retains_identity_failure_with_process_state(self):
        engine=types.SimpleNamespace(run=lambda *args,**kwargs:b'{"Running":true,"Status":"running","ExitCode":0}')
        store=types.SimpleNamespace(Engine=lambda:engine)
        with mock.patch.object(H.os,'geteuid',return_value=0),mock.patch.object(H,'source',return_value=(None,None,store)),mock.patch.object(H,'identity',side_effect=H.HouseholdError('household_identity_exec_failed')):
            result=H.diagnose_root()
        self.assertEqual(result['identity']['error'],'household_identity_exec_failed')
        self.assertTrue(result['services']['server']['running'])

class HouseholdStartupTests(unittest.TestCase):
    def waiter(self):
        import ast,re
        source=ast.parse((ROOT/'scripts/household/seed-agent.py').read_text())
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='wait_for_key')
        clock=types.SimpleNamespace(monotonic=mock.Mock(return_value=0),sleep=mock.Mock())
        namespace={'time':clock,'re':re};exec(compile(ast.Module(body=[function],type_ignores=[]),'key-wait-test','exec'),namespace)
        return namespace['wait_for_key'],clock

    def test_delayed_native_key_is_retried_before_use(self):
        wait,clock=self.waiter()
        path=types.SimpleNamespace(read_text=mock.Mock(side_effect=[FileNotFoundError(),'', 'a'*64+'\n']))
        self.assertEqual(wait(path,180),'a'*64)
        self.assertEqual(clock.sleep.call_count,2)

    def test_missing_or_invalid_key_has_bounded_wait(self):
        for value in (FileNotFoundError(),'private malformed value'):
            wait,clock=self.waiter();clock.monotonic.return_value=181
            read=mock.Mock(side_effect=value) if isinstance(value,Exception) else mock.Mock(return_value=value)
            with self.assertRaises(TimeoutError):wait(types.SimpleNamespace(read_text=read),180)
            clock.sleep.assert_not_called()

    def test_key_permission_error_is_not_retried_forever(self):
        wait,clock=self.waiter()
        with self.assertRaises(PermissionError):wait(types.SimpleNamespace(read_text=mock.Mock(side_effect=PermissionError())),180)
        clock.sleep.assert_not_called()

    def test_seed_failure_stage_survives_successful_transport_without_raw_values(self):
        for stage in ('native_key','backend','model_discovery','profile_activate','private-raw-message'):
            payload={'status':'failed','stage':stage,'error':'PRIVATE RAW CONTENT'}
            engine=types.SimpleNamespace(run=lambda *a,**kw:json.dumps(payload).encode())
            with self.assertRaises(H.HouseholdError) as error:H.seed_agent(engine,'agent-platform-household-alejandro')
            self.assertEqual(str(error.exception),'household_agent_seed_failed_'+('unknown' if stage=='private-raw-message' else stage))
            self.assertNotIn('PRIVATE',str(error.exception))

    def test_setup_step_preserves_fixed_phase_and_redacts_exception_messages(self):
        for cause,suffix in [('operation_failed','operation_failed'),('operation_unavailable_or_timed_out','unavailable_or_timed_out'),('private backend response','failed')]:
            with self.assertRaises(H.HouseholdError) as error:
                H.setup_step('seed_alejandro',mock.Mock(side_effect=RuntimeError(cause)))
            self.assertEqual(str(error.exception),'household_setup_seed_alejandro_'+suffix)

    def run_bootstrap(self, fail_activate=False, missing_final_model=False):
        import urllib.request,urllib.error
        code=(ROOT/'scripts/household/seed-agent.py').read_text()
        state={'key_reads':0,'marker':False,'api_calls':[],'settings_reads':0}
        class FakePath:
            def __init__(inner,value):inner.value=value
            def read_text(inner):
                state['key_reads']+=1
                if state['key_reads']<3:raise FileNotFoundError()
                return 'a'*64
            def exists(inner):return state['marker']
            def write_text(inner,value):state['marker']=True
            def chmod(inner,value):state['marker_mode']=value
        class Response(io.BytesIO):pass
        def open_request(request,**kwargs):
            url=request if isinstance(request,str) else request.full_url
            state['api_calls'].append(url)
            if url.endswith('/v1/models'):payload={'data':[{'id':'qwen3:8b'}]}
            elif url.endswith('/settings'):
                state['settings_reads']+=1
                payload={} if missing_final_model and state['settings_reads']>1 else {'agent_settings':{'llm':{'model':'openai/qwen3:8b'}}}
            elif url.endswith('/activate') and fail_activate:raise RuntimeError('PRIVATE provider failure with key')
            else:payload={}
            return Response(json.dumps(payload).encode())
        output=io.StringIO()
        with mock.patch('pathlib.Path',FakePath),mock.patch('urllib.request.build_opener',return_value=types.SimpleNamespace(open=open_request)),mock.patch('time.sleep'),mock.patch('time.monotonic',return_value=0),contextlib.redirect_stdout(output):
            exec(compile(code,'isolated-seed-test','exec'),{})
        self.assertNotIn('a'*64,output.getvalue());self.assertNotIn('PRIVATE',output.getvalue())
        return json.loads(output.getvalue()),state

    def test_actual_bootstrap_handles_first_start_key_race(self):
        result,state=self.run_bootstrap()
        self.assertEqual(result['status'],'passed');self.assertEqual(state['key_reads'],3)
        self.assertTrue(state['marker']);self.assertEqual(state['marker_mode'],0o600)

    def test_activation_failure_does_not_mark_bootstrap_complete(self):
        result,state=self.run_bootstrap(fail_activate=True)
        self.assertEqual(result['stage'],'profile_activate');self.assertFalse(state['marker'])

    def test_failed_settings_readback_does_not_write_marker(self):
        result,state=self.run_bootstrap(missing_final_model=True)
        self.assertEqual(result['stage'],'settings_readback');self.assertFalse(state['marker'])

class ModelRelayTests(unittest.TestCase):
    def discoverer(self):
        import ast,urllib.error
        source=ast.parse((ROOT/'scripts/household/seed-agent.py').read_text())
        nodes=[node for node in source.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in {'discover_model','DiscoveryError'}]
        clock=types.SimpleNamespace(monotonic=mock.Mock(return_value=0),sleep=mock.Mock())
        namespace={'time':clock,'json':json,'urllib':types.SimpleNamespace(error=urllib.error)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'discovery-test','exec'),namespace)
        return namespace['discover_model'],namespace['DiscoveryError'],clock

    def test_relay_config_routes_every_compiled_module_temp_area_to_tmp(self):
        text=H.model_config()
        for directive in ('client_body_temp_path','proxy_temp_path','fastcgi_temp_path','uwsgi_temp_path','scgi_temp_path'):
            self.assertRegex(text,directive+r' /tmp/[a-z_]+;')
        self.assertIn('pid /tmp/nginx.pid;',text)
        self.assertIn('limit_except POST { deny all; }',text)
        self.assertIn('location / { return 404; }',text)

    def test_current_ollama_model_response_is_accepted(self):
        discover,error,clock=self.discoverer()
        opener=types.SimpleNamespace(open=mock.Mock(return_value=io.BytesIO(b'{"data":[{"id":"qwen3:8b"}]}')))
        discover(opener,30);clock.sleep.assert_not_called()

    def test_transient_dns_and_503_retry_then_succeed(self):
        import urllib.error
        for failure in (urllib.error.URLError('private DNS context'),
                        urllib.error.HTTPError('http://example.invalid',503,'private response',{},io.BytesIO(b'private'))):
            discover,error,clock=self.discoverer()
            opener=types.SimpleNamespace(open=mock.Mock(side_effect=[failure,io.BytesIO(b'{"data":[{"id":"qwen3:8b"}]}')]))
            discover(opener,30)
            self.assertEqual(opener.open.call_count,2);clock.sleep.assert_called_once_with(1)

    def test_deadline_stops_network_retries_with_fixed_category(self):
        import urllib.error
        discover,error,clock=self.discoverer();clock.monotonic.return_value=31
        opener=types.SimpleNamespace(open=mock.Mock(side_effect=urllib.error.URLError('PRIVATE detail')))
        with self.assertRaises(error) as caught:discover(opener,30)
        self.assertEqual(str(caught.exception),'network_unavailable');clock.sleep.assert_not_called()

    def test_bad_schema_absent_model_and_invalid_json_are_not_retried(self):
        for raw,expected in [(b'{"data":[]}','model_not_listed'),(b'{"models":[]}','invalid_schema'),(b'PRIVATE non-JSON','invalid_json')]:
            discover,error,clock=self.discoverer()
            opener=types.SimpleNamespace(open=mock.Mock(return_value=io.BytesIO(raw)))
            with self.assertRaises(error) as caught:discover(opener,30)
            self.assertEqual(str(caught.exception),expected);clock.sleep.assert_not_called()

    def test_http_401_is_distinguished_without_printing_response(self):
        import urllib.error
        discover,error,clock=self.discoverer()
        opener=types.SimpleNamespace(open=mock.Mock(side_effect=urllib.error.HTTPError('http://example.invalid',401,'PRIVATE',{},io.BytesIO(b'PRIVATE'))))
        with self.assertRaises(error) as caught:discover(opener,30)
        self.assertEqual(str(caught.exception),'http_4xx');clock.sleep.assert_not_called()

    def test_reviewed_legacy_config_migrates_atomically_and_repeat_is_noop(self):
        import hashlib
        new=H.model_config().encode()
        old=new.replace(b' fastcgi_temp_path /tmp/fastcgi;\n uwsgi_temp_path /tmp/uwsgi;\n scgi_temp_path /tmp/scgi;\n',b'')
        self.assertEqual(hashlib.sha256(old).hexdigest(),H.LEGACY_MODEL_CONFIG_SHA256)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model-nginx.conf';path.write_bytes(old);path.chmod(0o644)
            original=Path.lstat
            def root_stat(item,*args,**kwargs):
                info=original(item,*args,**kwargs)
                if item==path:return types.SimpleNamespace(st_mode=info.st_mode,st_uid=0,st_nlink=1)
                return info
            verified=[]
            def protected(item,data,create):
                self.assertEqual(item.read_bytes(),data);verified.append(data)
            with mock.patch.object(Path,'lstat',root_stat):
                pilot=types.SimpleNamespace(protected_file=protected)
                H.prepare_model_control(path,pilot)
                inode=path.stat().st_ino
                H.prepare_model_control(path,pilot)
            self.assertEqual(path.read_bytes(),new);self.assertEqual(path.stat().st_ino,inode)
            self.assertEqual(verified,[old,new,new])

    def test_arbitrary_control_drift_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model-nginx.conf';path.write_text('unreviewed configuration');path.chmod(0o644)
            def reject(*args,**kwargs):raise H.HouseholdError('control_file_drift')
            pilot=types.SimpleNamespace(protected_file=reject)
            with self.assertRaises(H.HouseholdError):H.prepare_model_control(path,pilot)
            self.assertEqual(path.read_text(),'unreviewed configuration')

    def test_native_preflight_uses_pinned_image_and_readonly_nonroot_constraints(self):
        calls=[];engine=types.SimpleNamespace(run=lambda args,**kw:calls.append((args,kw)))
        H.validate_model_relay(engine,H.POLICY['tenants'][0],{'proxy':{'image':'synthetic-pinned-image'}})
        args,kwargs=calls[0]
        self.assertIn('--read-only',args);self.assertIn('--rm',args)
        self.assertEqual(args[args.index('--user')+1],'101:101')
        self.assertEqual(args[args.index('--cap-drop')+1],'ALL')
        self.assertEqual(args[-3:],['nginx','synthetic-pinned-image','-t'])
        self.assertEqual(kwargs['timeout'],30)

class EnrollmentFeedbackAndBrandTests(unittest.TestCase):
    policy=InvitationTests.policy
    # Reuse the exact expression harness, not a second implementation of its rules.
    def test_rejections_show_fixed_feedback_without_password_values(self):
        cases=[lambda i,g,p,d,e,v:d.update(password='short',password_repeat='short'),
               lambda i,g,p,d,e,v:d.update(password_repeat='different'),
               lambda i,g,p,d,e,v:g.attributes.update(invitation_generation='replaced')]
        for mutation in cases:
            passed,plan,data=self.policy(mutate=mutation)
            self.assertFalse(passed);self.assertEqual(len(self.last_policy_messages),1)
            self.assertNotIn(data.get('password',''),self.last_policy_messages[0])
            self.assertNotIn('synthetic',self.last_policy_messages[0])

    def test_short_password_message_explains_minimum(self):
        self.policy(mutate=lambda i,g,p,d,e,v:d.update(password='short',password_repeat='short'))
        self.assertIn('16',self.last_policy_messages[0])

    def test_success_has_no_warning_and_keeps_identity_allowlist(self):
        passed,plan,data=self.policy()
        self.assertTrue(passed);self.assertEqual(self.last_policy_messages,[])
        self.assertEqual(set(data),{'username','name','password','attributes'})

    def test_css_is_in_the_nondefault_household_brand_only(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        entries={row['id']:row for row in source.parse(H.blueprint('192.168.42.20'))['entries']}
        brand=entries['brand'];self.assertFalse(brand['attrs']['default'])
        self.assertEqual(brand['attrs']['branding_custom_css'],(ROOT/'infra/identity/household-light.css').read_text())
        css=brand['attrs']['branding_custom_css']
        self.assertNotIn('url(',css);self.assertNotIn('@import',css)
        self.assertNotIn('display: none',css);self.assertIn(':focus-visible',css)
        self.assertIn('#f5f7fb',css);self.assertIn('#ffffff',css)

    def test_approved_right_content_layout_preserves_native_flow_designations(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        flows=[row for row in source.parse(H.blueprint('192.168.42.20'))['entries'] if row['model']=='authentik_flows.flow']
        self.assertEqual(len(flows),5)
        self.assertTrue(all(row['attrs']['layout']=='content_right' for row in flows))
        self.assertEqual({row['identifiers']['slug']:row['attrs']['designation'] for row in flows},
            {'family-login':'authentication','family-authorize':'authorization','family-logout':'invalidation',
             'family-enroll-alejandro':'enrollment','family-enroll-kimberly':'enrollment'})

    def test_identity_only_apply_never_starts_agents_or_issues_invitations(self):
        payload={'action':'apply','blueprint':'synthetic'}
        with mock.patch.object(H,'identity_payload',return_value=payload),mock.patch.object(H,'check_public_brand',return_value={'public_https_brand':'passed'}),mock.patch.object(H,'check_public_browser_routes',return_value={'public_login_redirects':'passed'}),mock.patch.object(H,'root_call',return_value={'status':'passed'}) as call:
            result=H.owner_identity_apply()
        call.assert_called_once_with('root-status',payload)
        self.assertEqual(result['status'],'passed')

class BrandNativeReadbackTests(unittest.TestCase):
    def setUp(self):
        import ast
        source=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='apply_brand_appearance')
        self.namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'brand-native-readback-test','exec'),self.namespace)
        self.apply=self.namespace['apply_brand_appearance']
        self.css='/* Approved design */\nbody { color: blue; }\n'
        self.brand=types.SimpleNamespace(default=False,branding_custom_css=self.css.strip(),
            attributes={'retained':'yes','settings':{'locale':'es','theme':{'base':'dark','other':'preserved'}}},
            save=mock.Mock(),refresh_from_db=mock.Mock())
        self.flows=[types.SimpleNamespace(slug=name,layout='content_right') for name in
                    ('family-login','family-authorize','family-logout','family-enroll-alejandro','family-enroll-kimberly')]

    def test_reproduces_strict_comparison_false_negative_after_serializer_trim(self):
        self.assertNotEqual(self.brand.branding_custom_css,self.css)
        self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.brand.attributes['settings']['theme']['base'],'light')

    def test_internal_css_change_is_rejected_before_save(self):
        self.brand.branding_custom_css=self.css.replace('blue','red')
        with self.assertRaises(AssertionError):self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.namespace['stage'],'brand_css');self.brand.save.assert_not_called()

    def test_default_admin_brand_is_rejected_before_save(self):
        self.brand.default=True
        with self.assertRaises(AssertionError):self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.namespace['stage'],'brand_scope');self.brand.save.assert_not_called()

    def test_theme_merge_preserves_existing_preferences(self):
        self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.brand.attributes,{'retained':'yes','settings':{'locale':'es','theme':{'base':'light','other':'preserved'}}})
        self.brand.save.assert_called_once();self.brand.refresh_from_db.assert_called_once()

    def test_theme_drift_has_its_own_fixed_stage(self):
        self.brand.refresh_from_db=lambda:self.brand.attributes['settings']['theme'].update(base='dark')
        with self.assertRaises(AssertionError):self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.namespace['stage'],'brand_theme_readback')

    def test_layout_drift_identifies_exact_reserved_flow(self):
        self.flows[-1].layout='stacked'
        with self.assertRaises(AssertionError):self.apply(self.brand,self.css,self.flows)
        self.assertEqual(self.namespace['stage'],'brand_layout_family_enroll_kimberly')
        self.assertIn(self.namespace['stage'],H.IDENTITY_STAGES)

    def test_non_text_css_is_rejected_before_save(self):
        self.brand.branding_custom_css=None
        with self.assertRaises(AssertionError):self.apply(self.brand,self.css,self.flows)
        self.brand.save.assert_not_called()

class BrandOriginTests(unittest.TestCase):
    def migration(self,legacy=None,target=None):
        import ast
        source=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='migrate_brand_origin')
        namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'brand-origin-test','exec'),namespace)
        def find(**kwargs):return types.SimpleNamespace(first=lambda:target if kwargs['domain'].endswith(':8443') else legacy)
        Brand=types.SimpleNamespace(objects=types.SimpleNamespace(filter=find))
        return lambda:namespace['migrate_brand_origin'](Brand,'https://192.168.42.20:8443')

    def brand(self,default=False,slug='family-login'):
        return types.SimpleNamespace(default=default,domain='192.168.42.20',flow_authentication=types.SimpleNamespace(slug=slug),save=mock.Mock())

    def test_renames_existing_brand_without_creating_or_deleting(self):
        brand=self.brand();self.migration(legacy=brand)()
        self.assertEqual(brand.domain,'192.168.42.20:8443');brand.save.assert_called_once()

    def test_repeat_does_not_overwrite_existing_correct_brand(self):
        brand=self.brand();brand.domain='192.168.42.20:8443'
        self.migration(target=brand)();brand.save.assert_not_called()

    def test_collision_default_and_unmanaged_brand_are_refused(self):
        for legacy,target in [(self.brand(),self.brand()),(self.brand(default=True),None),(self.brand(slug='admin-login'),None)]:
            with self.assertRaises(AssertionError):self.migration(legacy,target)()
            legacy.save.assert_not_called()

    def test_blueprint_matches_exact_browser_host_with_port(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        brand=next(row for row in source.parse(H.blueprint('192.168.42.20'))['entries'] if row['id']=='brand')
        self.assertEqual(brand['identifiers']['domain'],'192.168.42.20:8443')
        self.assertFalse(brand['attrs']['default'])

    def test_live_check_rejects_default_brand_and_wrong_styles(self):
        import ssl
        gateway=types.SimpleNamespace(state=lambda:(Path('/synthetic'),{'address':'192.168.42.20'}))
        expected=(ROOT/'infra/identity/household-light.css').read_text()
        good={'matched_domain':'192.168.42.20:8443','ui_theme':'light','branding_custom_css':expected.strip()}
        for data,passed in [(good,True),({**good,'matched_domain':'authentik-default'},False),
                            ({**good,'ui_theme':'automatic'},False),({**good,'branding_custom_css':''},False)]:
            opener=types.SimpleNamespace(open=lambda *a,**kw:io.BytesIO(json.dumps(data).encode()))
            with mock.patch.object(H,'source',return_value=(gateway,None,None)),mock.patch.object(H.ssl,'create_default_context'),mock.patch.object(H.urllib.request,'build_opener',return_value=opener):
                if passed:self.assertEqual(H.check_public_brand()['public_https_brand'],'passed')
                else:
                    with self.assertRaises(H.HouseholdError):H.check_public_brand()

class PromptSessionContextTests(unittest.TestCase):
    policy=InvitationTests.policy

    def test_real_prompt_context_with_session_but_without_flow_plan_is_accepted(self):
        passed,plan,data=self.policy(user='alejandro')
        self.assertTrue(passed)
        self.assertNotIn('flow_plan',self.policy_request.context)
        self.assertIs(self.policy_request.http_request.session['authentik/flows/plan'],plan)
        self.assertEqual(data['username'],'alejandro')
        self.assertEqual(plan.context['prompt_data'],{})

    def test_consumed_invite_object_in_existing_session_can_continue(self):
        # InvitationStage deletes the row (pk=None) but retains the invitation in the plan.
        passed,plan,data=self.policy()
        self.assertIsNone(plan.context['invitation'].pk)
        self.assertTrue(passed)

    def test_context_injection_without_a_session_does_not_authorize(self):
        def mutate(i,g,p,d,e,v):
            self.policy_request.context['flow_plan']=p
            self.policy_request.http_request.session.clear()
        passed,_,_=self.policy(mutate=mutate)
        self.assertFalse(passed);self.assertTrue(self.last_policy_messages)

    def test_missing_http_request_is_denied(self):
        passed,_,_=self.policy(mutate=lambda i,g,p,d,e,v:setattr(self.policy_request,'http_request',None))
        self.assertFalse(passed)

    def test_route_must_match_the_reserved_enrollment_flow(self):
        def mutate(i,g,p,d,e,v):self.policy_request.http_request.resolver_match.kwargs['flow_slug']='family-enroll-alejandro'
        passed,_,_=self.policy(user='kimberly',mutate=mutate)
        self.assertFalse(passed)

    def test_session_plan_and_invitation_flow_must_match(self):
        passed,_,_=self.policy(mutate=lambda i,g,p,d,e,v:setattr(p,'flow_pk','22222222222222222222222222222222'))
        self.assertFalse(passed)

if __name__=='__main__':unittest.main()


class InvitationSessionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        import ast
        tree=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='invitation_plan_summary')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'invitation-summary','exec'),ns)
        self.summarize=ns['invitation_plan_summary']
        self.invite=types.SimpleNamespace(name='family-invite-alejandro',flow=types.SimpleNamespace(slug='family-enroll-alejandro'),fixed_data={'generation':'a'*64})
        self.group=types.SimpleNamespace(is_superuser=False,attributes={'invitation_generation':'a'*64})
        self.plan=types.SimpleNamespace(context={'invitation':self.invite,'invitation_in_effect':True,
            'password':'PRIVATE-PASSWORD','cookie':'PRIVATE-COOKIE'})

    def test_valid_session_reports_only_safe_booleans(self):
        result=self.summarize(self.plan,'alejandro',self.group)
        self.assertTrue(result['generation_matches'])
        self.assertTrue(all(type(v) is bool for v in result.values()))
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('a'*64,json.dumps(result))

    def test_replaced_generation_is_distinct_from_missing_registry(self):
        self.group.attributes['invitation_generation']='b'*64
        result=self.summarize(self.plan,'alejandro',self.group)
        self.assertTrue(result['group_generation_valid']);self.assertFalse(result['generation_matches'])
        self.group.attributes={}
        result=self.summarize(self.plan,'alejandro',self.group)
        self.assertFalse(result['group_generation_valid']);self.assertTrue(result['invitation_generation_valid'])

    def test_missing_invitation_generation_is_distinct_from_missing_group_generation(self):
        self.invite.fixed_data={}
        result=self.summarize(self.plan,'alejandro',self.group)
        self.assertFalse(result['invitation_generation_valid']);self.assertTrue(result['group_generation_valid'])
        self.assertFalse(result['generation_matches'])

    def test_other_user_and_unrelated_session_are_not_reported(self):
        self.assertIsNone(self.summarize(self.plan,'kimberly',self.group))
        self.assertIsNone(self.summarize(None,'alejandro',self.group))
        self.invite.flow.slug='family-login'
        self.assertIsNone(self.summarize(self.plan,'alejandro',self.group))

    def test_malformed_generation_does_not_match_or_expose_values(self):
        for value in (None,[],{},64,'short'):
            self.invite.fixed_data={'generation':value}
            result=self.summarize(self.plan,'alejandro',self.group)
            self.assertFalse(result['invitation_generation_valid']);self.assertFalse(result['generation_matches'])


class InvitationEntryURLTests(unittest.TestCase):
    def setUp(self):
        import ast
        tree=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='invitation_entry_url')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'invitation-entry','exec'),ns)
        self.entry=ns['invitation_entry_url'];self.token='11111111-1111-1111-1111-111111111111'

    def test_both_users_start_via_cancel_with_exact_relative_single_token_target(self):
        from urllib.parse import urlsplit,parse_qs
        for user in ('alejandro','kimberly'):
            entry=urlsplit(self.entry('https://192.168.42.20:8443',user,self.token))
            self.assertEqual((entry.scheme,entry.netloc,entry.path),('https','192.168.42.20:8443','/flows/-/cancel/'))
            query=parse_qs(entry.query,strict_parsing=True);self.assertEqual(set(query),{'next'})
            target=urlsplit(query['next'][0])
            self.assertEqual((target.scheme,target.netloc,target.fragment),('','',''))
            self.assertEqual(target.path,'/if/flow/family-enroll-'+user+'/')
            self.assertEqual(parse_qs(target.query),{'itoken':[self.token]})

    def test_external_ambiguous_or_wrong_port_origins_are_rejected(self):
        for origin in ('http://192.168.42.20:8443','https://192.168.42.20:443',
            'https://example.com:8443','https://8.8.8.8:8443','https://127.0.0.1:8443',
            'https://user@192.168.42.20:8443','https://192.168.42.20:8443/elsewhere',
            'https://192.168.42.20:8443/?next=//external.invalid','https://192.168.42.20:8443/#fragment'):
            with self.subTest(origin=origin),self.assertRaises((AssertionError,ValueError)):
                self.entry(origin,'alejandro',self.token)

    def test_unreserved_users_and_token_query_injection_are_rejected(self):
        for user,token in [('akadmin',self.token),('../kimberly',self.token),
                           ('alejandro',self.token+'&next=//external.invalid')]:
            with self.assertRaises((AssertionError,ValueError)):
                self.entry('https://192.168.42.20:8443',user,token)

    def test_trailing_origin_slash_is_normalized(self):
        self.assertEqual(self.entry('https://192.168.42.20:8443/','alejandro',self.token),
                         self.entry('https://192.168.42.20:8443','alejandro',self.token))


class EnrollmentDestinationTests(unittest.TestCase):
    policy=InvitationTests.policy

    def test_success_selects_only_reserved_personal_app_despite_injected_destination(self):
        for user,port in [('alejandro',8444),('kimberly',8445)]:
            passed,plan,data=self.policy(user,mutate=lambda i,g,p,d,e,v:d.update(redirect='https://external.invalid',next='//external.invalid'))
            self.assertTrue(passed)
            self.assertEqual(plan.context['redirect'],f'https://192.168.42.20:{port}/canvas')
            self.assertNotIn('redirect',data);self.assertNotIn('next',data)

    def test_failed_registration_does_not_install_a_destination(self):
        mutations=[lambda i,g,p,d,e,v:d.update(password='short'),
                   lambda i,g,p,d,e,v:g.attributes.clear(),
                   lambda i,g,p,d,e,v:setattr(e,'exists',lambda:True)]
        for change in mutations:
            passed,plan,_=self.policy(mutate=change)
            self.assertFalse(passed);self.assertNotIn('redirect',plan.context)

    def test_compiled_blueprint_has_correct_destinations_and_external_users_with_totp_before_login(self):
        source=H.helpers()[0].pki().backup().local_module().native().source_module()
        entries={row['id']:row for row in source.parse(H.blueprint('192.168.42.20'))['entries']}
        for user,port in [('alejandro',8444),('kimberly',8445)]:
            expr=entries['invite-policy-'+user]['attrs']['expression']
            self.assertIn(f'plan.context["redirect"] = "https://192.168.42.20:{port}/canvas"',expr)
            self.assertNotIn('__APPLICATION_URL__',expr)
            self.assertEqual(entries['invite-write-'+user]['attrs']['user_type'],'external')
            self.assertEqual(entries['enroll-totp-'+user]['identifiers']['order'],40)
            self.assertEqual(entries['enroll-session-'+user]['identifiers']['order'],50)


class PublicBrowserRouteTests(unittest.TestCase):
    def run_probe(self,location,status=302):
        self.seen=[]
        gateway=types.SimpleNamespace(state=lambda:(Path('/synthetic'),{'address':'192.168.42.20'}))
        def open_url(url,**kwargs):
            self.seen.append(url)
            raise H.urllib.error.HTTPError(url,status,'omitted',{'Location':location},None)
        opener=types.SimpleNamespace(open=open_url)
        with mock.patch.object(H,'source',return_value=(gateway,None,None)),mock.patch.object(H.ssl,'create_default_context'),mock.patch.object(H.urllib.request,'build_opener',return_value=opener),mock.patch.object(H.time,'sleep'),contextlib.redirect_stdout(io.StringIO()) as output:
            try:return H.check_public_browser_routes()
            finally:self.output=output.getvalue()

    def test_both_personal_origins_redirect_to_public_https_authorization(self):
        result=self.run_probe('https://192.168.42.20:8443/application/o/authorize/?state=PRIVATE-STATE')
        self.assertEqual(result,{'public_login_redirects':'passed'})
        self.assertEqual(len(self.seen),2)
        self.assertTrue(self.seen[0].startswith('https://192.168.42.20:8444/'))
        self.assertTrue(self.seen[1].startswith('https://192.168.42.20:8445/'))
        self.assertNotIn('PRIVATE',json.dumps(result)+self.output)

    def test_observed_localhost_and_other_untrusted_redirects_are_rejected(self):
        for location in ('http://localhost:9000/application/o/authorize/?state=PRIVATE',
            'http://192.168.42.20:8443/application/o/authorize/',
            'https://external.invalid/application/o/authorize/',
            '//192.168.42.20:8443/application/o/authorize/',
            'https://user@192.168.42.20:8443/application/o/authorize/',
            'https://192.168.42.20:8443/if/admin/',
            'https://192.168.42.20:8443/application/o/authorize/#fragment'):
            with self.subTest(location=location),self.assertRaises(H.HouseholdError) as error:self.run_probe(location)
            self.assertEqual(str(error.exception),'household_public_login_redirect_invalid')
            self.assertNotIn('PRIVATE',self.output);self.assertEqual(len(self.seen),6)

    def test_success_response_without_an_authorization_redirect_is_not_accepted(self):
        with self.assertRaises(H.HouseholdError):self.run_probe('https://192.168.42.20:8443/application/o/authorize/',status=200)
