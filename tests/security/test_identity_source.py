"""Mutations of the actual candidate blueprint; no simulated browser login claims."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('identity_source',ROOT/'scripts/identity/check-source.py')
P=importlib.util.module_from_spec(spec);sys.modules[spec.name]=P;spec.loader.exec_module(P)

class IdentitySourceTests(unittest.TestCase):
    def setUp(self):
        self.raw=P.BLUEPRINT.read_bytes();self.doc=P.parse(self.raw)
        self.rows={r['id']:r for r in self.doc['entries']}
    def reject(self,change):
        document=copy.deepcopy(self.doc);rows={r['id']:r for r in document['entries']}
        change(document,rows)
        with self.assertRaises(P.InvalidSource):P.validate(document)
    def test_source_pass_is_explicitly_not_login_or_native_acceptance(self):
        report=P.validate(self.doc)
        self.assertEqual(report['status'],'prepared')
        for field in ('native_authentik_validation','browser_mfa_acceptance','gateway_authorization_acceptance','household_readiness'):
            self.assertEqual(report[field],'pending')
    def test_each_required_entry_cannot_be_removed(self):
        for row in self.doc['entries']:
            with self.subTest(entry=row['id']):
                self.reject(lambda d,r:d['entries'].remove(r[row['id']]))
    def test_no_mfa_skip_or_cached_validation(self):
        for id in ('mfa-login','mfa-access'):
            for field,value in [('not_configured_action','skip'),('device_classes',['email']),('last_auth_threshold','hours=24'),('webauthn_user_verification','preferred')]:
                with self.subTest(stage=id,field=field):
                    self.reject(lambda d,r:r[id]['attrs'].update({field:value}))
    def test_missing_enrollment_stages_and_webauthn_without_verification_rejected(self):
        self.reject(lambda d,r:r['mfa-login']['attrs'].update(configuration_stages=[]))
        self.reject(lambda d,r:r['webauthn']['attrs'].update(user_verification='discouraged'))
    def test_login_cannot_be_created_before_password_and_mfa(self):
        for stage in ('login-password','login-mfa-login','login-session'):
            with self.subTest(stage=stage):
                self.reject(lambda d,r:r[stage]['identifiers'].update(order=1))
        self.reject(lambda d,r:r['login-mfa-login']['attrs'].update(evaluate_on_plan=True))
    def test_no_optional_policy_on_mfa_stage(self):
        self.reject(lambda d,r:d['entries'].append({'id':'skip-mfa','model':'authentik_policies.policybinding','identifiers':{'target':P.Ref('login-mfa-login'),'order':10},'attrs':{'enabled':True}}))
    def test_foreign_provider_or_group_mapping_rejected_for_both_apps(self):
        for own,other in [('probe-a','probe-b'),('probe-b','probe-a')]:
            with self.subTest(tenant=own):
                self.reject(lambda d,r:r['app-'+own]['attrs'].update(provider=P.Ref('provider-'+other)))
                self.reject(lambda d,r:r['allow-'+own]['identifiers'].update(group=P.Ref('group-'+other)))
    def test_disabled_negated_or_fail_open_group_binding_rejected(self):
        for field,value in [('enabled',False),('negate',True),('failure_result',True)]:
            self.reject(lambda d,r:r['allow-probe-a']['attrs'].update({field:value}))
    def test_domain_auth_skip_paths_basic_and_header_auth_rejected(self):
        for field,value in [('mode','forward_domain'),('skip_path_regex','.*'),('intercept_header_auth',True),('basic_auth_enabled',True),('cookie_domain','home.arpa')]:
            self.reject(lambda d,r:r['provider-probe-a']['attrs'].update({field:value}))
    def test_public_foreign_or_cross_application_hosts_rejected(self):
        for url in ('http://probe-a.home.arpa','https://public.example','https://probe-b.home.arpa'):
            self.reject(lambda d,r:r['provider-probe-a']['attrs'].update(external_host=url))
    def test_admin_group_membership_or_credentials_cannot_be_bundled(self):
        for field,value in [('is_superuser',True),('users',['private-user']),('parents',['admins']),('password','private-value')]:
            self.reject(lambda d,r:r['group-probe-a']['attrs'].update({field:value}))
    def test_alternative_login_enrollment_recovery_and_long_session_rejected(self):
        self.reject(lambda d,r:r['identify']['attrs'].update(sources=['external-source']))
        self.reject(lambda d,r:r['brand']['attrs'].update(flow_authentication=P.Ref('other-login')))
        self.reject(lambda d,r:r['brand']['attrs'].update(flow_recovery=P.Ref('password-only')))
        self.reject(lambda d,r:r['session']['attrs'].update(session_duration='days=365'))
    def test_no_auto_apply_duplicate_ids_or_conditional_entries(self):
        self.reject(lambda d,r:d['metadata']['labels'].update({'blueprints.goauthentik.io/instantiate':'true'}))
        self.reject(lambda d,r:d['entries'].append(copy.deepcopy(d['entries'][0])))
        self.reject(lambda d,r:r['allow-probe-a'].update(conditions=[False]))
    def test_yaml_duplicate_keys_unsafe_tags_aliases_and_oversize_rejected(self):
        for raw in (b'version: 1\nversion: 2',b'key: !Env PRIVATE',b'key: !File /etc/passwd',b'key: !!python/object:os {}',b'a: &a []\nb: *a',b'x'*32769):
            with self.subTest(case=raw[:12]):
                with self.assertRaises(P.InvalidSource):P.parse(raw)
    def test_plain_string_cannot_impersonate_reference_and_boolean_is_not_order(self):
        self.reject(lambda d,r:r['app-probe-a']['attrs'].update(provider='provider-probe-a'))
        self.reject(lambda d,r:r['allow-probe-a']['identifiers'].update(order=True))
    def test_outpost_requires_proxy_type_and_no_service_connection(self):
        self.reject(lambda d,r:r['outpost']['attrs'].pop('type'))
        self.reject(lambda d,r:r['outpost']['attrs'].update(type='ldap'))
        self.reject(lambda d,r:r['outpost']['attrs'].update(service_connection='docker-daemon'))

    def test_entry_order_is_not_a_hidden_dependency_of_guard(self):
        self.doc['entries'].reverse();self.assertEqual(P.validate(self.doc)['source_contract'],'passed')
    def test_cli_only_reports_fixed_summary_without_identity_or_credentials(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/identity/check-source.py')],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0)
        self.assertNotIn('entries',result.stdout)
        self.assertIn('"household_readiness": "pending"',result.stdout)

if __name__=='__main__':unittest.main()
