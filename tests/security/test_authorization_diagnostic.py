"""Post-login diagnostics distinguish missing OAuth continuation without exposing state."""
import ast,json,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

class AuthorizationDiagnosticTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='authorization_plan_summary')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'authorization-summary','exec'),ns)
        self.summarize=ns['authorization_plan_summary']
        self.flows={'authorize-id':'family-authorize','login-id':'family-login'}
        self.context={'pending_user':types.SimpleNamespace(username='alejandro'),
            'goauthentik.io/providers/oauth2/params':{'state':'PRIVATE-STATE','code':'PRIVATE-CODE'},
            'application':types.SimpleNamespace(secret='PRIVATE-APPLICATION'),
            'password':'PRIVATE-PASSWORD'}
        completion=type('OAuthFulfillmentStage',(),{})
        self.plan=types.SimpleNamespace(flow_pk='authorize-id',context=self.context,bindings=[
            types.SimpleNamespace(stage=types.SimpleNamespace(name='family-mfa-access',view=object)),
            types.SimpleNamespace(stage=types.SimpleNamespace(name='PRIVATE-NAME',view=completion))])

    def test_authorization_retains_completion_and_redacts_values(self):
        result=self.summarize(self.plan,self.flows)
        self.assertEqual(result,{'username':'alejandro','flow':'family-authorize','mfa_pending':True,
            'oauth_parameters_present':True,'oauth_completion_pending':True,'application_context_present':True})
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_bare_flow_is_distinguished_from_oauth_authorization(self):
        self.context.pop('goauthentik.io/providers/oauth2/params');self.context.pop('application')
        self.plan.bindings=self.plan.bindings[:1]
        result=self.summarize(self.plan,self.flows)
        self.assertTrue(result['mfa_pending']);self.assertFalse(result['oauth_parameters_present'])
        self.assertFalse(result['oauth_completion_pending']);self.assertFalse(result['application_context_present'])

    def test_completed_mfa_is_not_reported_pending(self):
        self.plan.bindings=self.plan.bindings[1:]
        self.assertFalse(self.summarize(self.plan,self.flows)['mfa_pending'])

    def test_unrelated_or_malformed_plans_are_not_exported(self):
        self.assertIsNone(self.summarize(None,self.flows))
        self.plan.flow_pk='other';self.assertIsNone(self.summarize(self.plan,self.flows))
        self.plan.flow_pk='authorize-id';self.context['pending_user'].username='akadmin'
        self.assertIsNone(self.summarize(self.plan,self.flows))

    def test_login_plan_does_not_claim_oauth_completion(self):
        self.plan.flow_pk='login-id';self.plan.bindings=self.plan.bindings[:1]
        self.plan.bindings[0].stage.name='family-mfa-login'
        self.context.pop('goauthentik.io/providers/oauth2/params');self.context.pop('application')
        result=self.summarize(self.plan,self.flows)
        self.assertEqual(result['flow'],'family-login');self.assertTrue(result['mfa_pending'])
        self.assertFalse(result['oauth_completion_pending'])

    def test_native_authorize_plan_can_use_authenticated_session_user(self):
        # OAuth planning does not require pending_user in its context.
        self.context.pop('pending_user')
        result=self.summarize(self.plan,self.flows,'alejandro')
        self.assertEqual(result['username'],'alejandro')
        self.assertTrue(result['oauth_completion_pending'])
        self.assertIsNone(self.summarize(self.plan,self.flows,'akadmin'))


class TotpRuntimeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        import datetime
        self.now=datetime.datetime.now(datetime.timezone.utc)
        tree=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='totp_runtime_summary')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'totp-summary','exec'),ns)
        self.summarize=ns['totp_runtime_summary']

    def device(self,seconds,allowed=True):
        import datetime
        class MetadataOnly:
            def __getattr__(self,name):
                raise AssertionError('Diagnostic must not access '+name)
        device=MetadataOnly()
        device.last_used=self.now-datetime.timedelta(seconds=seconds) if seconds is not None else None
        device.verify_is_allowed=lambda:(allowed,{'private':'PRIVATE'})
        return device

    def test_recent_success_and_throttle_are_independent(self):
        result=self.summarize([self.device(15),self.device(900,False)],self.now)
        self.assertEqual(result,{'confirmed_devices':2,'devices_verified_last_10m':1,'devices_temporarily_blocked':1})
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_no_success_or_future_timestamp_is_not_recent(self):
        result=self.summarize([self.device(None),self.device(-30)],self.now)
        self.assertEqual(result['devices_verified_last_10m'],0)

    def test_missing_device_is_distinct_from_rejected_code(self):
        self.assertEqual(self.summarize([],self.now),{'confirmed_devices':0,
            'devices_verified_last_10m':0,'devices_temporarily_blocked':0})


class MfaFailureEventDiagnosticTests(unittest.TestCase):
    def setUp(self):
        import datetime
        self.now=datetime.datetime.now(datetime.timezone.utc)
        tree=ast.parse((ROOT/'scripts/household/identity-native.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='mfa_failure_summary')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'mfa-failures','exec'),ns)
        self.summarize=ns['mfa_failure_summary']

    def event(self,age,context):
        import datetime
        return types.SimpleNamespace(created=self.now-datetime.timedelta(seconds=age),context=context)

    def test_mfa_rejection_is_distinct_from_password_failure(self):
        result=self.summarize([self.event(18,{'args':{'device_class':'totp'},'code':'PRIVATE'}),
            self.event(4,{'args':{'device_class':'password'}})],self.now,'args')
        self.assertEqual(result,{'totp_rejections_last_15m':1,'last_totp_rejection_age_seconds':18})
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_stale_future_and_malformed_events_are_not_recent_rejections(self):
        events=[self.event(901,{'args':{'device_class':'totp'}}),
            self.event(-5,{'args':{'device_class':'totp'}}),self.event(4,None),
            self.event(4,{'args':'PRIVATE'})]
        self.assertEqual(self.summarize(events,self.now,'args'),
            {'totp_rejections_last_15m':0,'last_totp_rejection_age_seconds':None})

    def test_most_recent_matching_event_does_not_depend_on_input_order(self):
        events=[self.event(age,{'args':{'device_class':'totp'}}) for age in (90,5,40)]
        self.assertEqual(self.summarize(events,self.now,'args')['last_totp_rejection_age_seconds'],5)
