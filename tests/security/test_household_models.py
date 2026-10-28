"""Native connection/profile diagnostics remain read-only and credential-free."""
import importlib.util,io,json,types,unittest,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_model_check',ROOT/'scripts/household/check-models.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
class ModelChecks(unittest.TestCase):
    def test_correct_backend_settings_and_version_report_only_booleans(self):
        def api(path):
            if path=='/server_info':return {'version':'1.53.0','PRIVATE':'omitted'}
            return {'agent_settings':{'llm':{'model':M.EXPECTED_MODEL,'base_url':M.EXPECTED_BASE,'api_key':'PRIVATE'}},'llm_api_key_is_set':True,'active_profile':'local-qwen3-8b'}
        result=M.check_backend(api)
        self.assertTrue(result['settings']['qwen_selected']);self.assertTrue(result['settings']['model_relay_selected'])
        self.assertTrue(result['settings']['llm_key_configured']);self.assertEqual(result['server_info']['status'],'passed')
        self.assertNotIn('PRIVATE',json.dumps(result))
    def test_working_backend_with_other_model_is_not_claimed_qwen(self):
        result=M.check_backend(lambda p:{'version':'1.53.0'} if p=='/server_info' else {'agent_settings':{'llm':{'model':'PRIVATE CUSTOM'}}})
        self.assertEqual(result['settings']['status'],'passed');self.assertFalse(result['settings']['qwen_selected'])
        self.assertNotIn('PRIVATE',json.dumps(result))
    def test_auth_network_and_schema_failures_are_distinct_without_raw_content(self):
        for cause,category in [(urllib.error.HTTPError('http://PRIVATE',401,'PRIVATE',{},io.BytesIO(b'PRIVATE')),'http_4xx'),
                               (OSError('PRIVATE'),'unavailable'),(ValueError('PRIVATE'),'invalid_schema')]:
            def api(path):raise cause
            result=M.check_backend(api)
            self.assertEqual(result['settings']['category'],category);self.assertNotIn('PRIVATE',json.dumps(result))
    def test_invalid_server_version_is_not_accepted(self):
        result=M.check_backend(lambda p:{'version':'PRIVATE'} if p=='/server_info' else {})
        self.assertEqual(result['server_info']['status'],'invalid_version_schema')
    def test_model_and_agent_profile_links_are_checked_without_exposing_keys(self):
        def api(path):
            if path.startswith('/api/agent-profiles'):return {'profile':{'llm_profile_ref':'local-qwen3-8b','PRIVATE':'hidden'}}
            return {'config':{'model':M.EXPECTED_MODEL,'base_url':M.EXPECTED_BASE,'api_key':'PRIVATE'},'api_key_set':True}
        result=M.profile_checks(api)
        self.assertTrue(result['qwen_profile']['key_configured']);self.assertTrue(result['default_agent']['references_qwen'])
        self.assertNotIn('PRIVATE',json.dumps(result))
    def test_missing_profile_is_reported_without_creation(self):
        calls=[]
        def api(path):calls.append(path);raise FileNotFoundError('PRIVATE')
        result=M.profile_checks(api)
        self.assertEqual(result['default_agent']['status'],'unavailable')
        self.assertEqual(calls,['/api/profiles/local-qwen3-8b','/api/agent-profiles/default'])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_probe_uses_exact_native_paths_and_response_flag(self):
        calls=[]
        def api(path):
            calls.append(path)
            if path=='/server_info':return {'version':'1.53.0'}
            if path=='/api/settings':return {'llm_api_key_is_set':True,'agent_settings':{'llm':{}}}
            raise AssertionError('unexpected native route')
        result=M.check_backend(api)
        self.assertEqual(calls,['/api/settings','/server_info'])
        self.assertTrue(result['settings']['llm_key_configured'])
        self.assertEqual(result['server_info']['status'],'passed')
    def test_frontend_only_key_alias_is_not_treated_as_native_evidence(self):
        result=M.check_backend(lambda path:{'version':'1.53.0'} if path=='/server_info' else {'llm_api_key_set':True})
        self.assertFalse(result['settings']['llm_key_configured'])
