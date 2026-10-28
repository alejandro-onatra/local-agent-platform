"""Managed profile tuning preserves credentials, custom values and user selection."""
import copy,importlib.util,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('tune_model',R/'scripts/household/tune-model.py')
T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)

class TuningTests(unittest.TestCase):
    def setUp(self):
        self.config={'model':'openai/qwen3:8b','base_url':'http://model-relay:8080/v1',
            'api_key':'PRIVATE-KEY','temperature':0.37,'extra_body':{'think':False,'other':12}}
        self.settings={'active_profile':T.PROFILE,'agent_settings':{'llm':copy.deepcopy(self.config)}}
        self.writes=[];self.exposures=0

    def api(self,path,body=None,expose=False):
        if path=='/api/settings':return copy.deepcopy(self.settings)
        if path.endswith('/activate'):
            self.writes.append(path);self.settings['agent_settings']['llm']=copy.deepcopy(self.config);return {}
        if body is not None:
            self.writes.append(path);self.config=copy.deepcopy(body['llm']);return {}
        if expose:self.exposures+=1
        data=copy.deepcopy(self.config)
        if not expose:data['api_key']=None
        return {'config':data}

    def test_preserves_key_and_unrelated_options_and_reports_no_secrets(self):
        result=T.tune(self.api)
        self.assertEqual(self.config['api_key'],'PRIVATE-KEY')
        self.assertEqual(self.config['temperature'],0.37)
        self.assertEqual(self.config['extra_body'],{'other':12})
        self.assertEqual(self.config['reasoning_effort'],'none')
        self.assertEqual(self.settings['agent_settings']['llm']['reasoning_effort'],'none')
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_foreign_model_or_endpoint_is_never_written(self):
        for field,value in [('model','openai/another'),('base_url','https://remote.invalid')]:
            original=copy.deepcopy(self.config);self.config[field]=value
            with self.assertRaises(ValueError):T.tune(self.api)
            self.assertEqual(self.writes,[]);self.assertEqual(self.exposures,0)
            self.config=original

    def test_other_active_selection_is_preserved(self):
        self.settings['active_profile']='other'
        result=T.tune(self.api)
        self.assertFalse(result['active_defaults_updated'])
        self.assertEqual(self.settings['active_profile'],'other')
        self.assertFalse(any(p.endswith('/activate') for p in self.writes))

    def test_repeat_does_not_rewrite_profile_or_read_secret(self):
        T.tune(self.api);self.writes=[];self.exposures=0
        result=T.tune(self.api)
        self.assertFalse(result['profile_changed']);self.assertEqual(self.exposures,0)
        self.assertEqual(self.writes,['/api/profiles/'+T.PROFILE+'/activate'])

    def test_failed_readback_is_not_reported_as_success(self):
        def api(path,body=None,expose=False):
            result=self.api(path,body,expose)
            if path.endswith('/activate'):self.config['reasoning_effort']='high'
            return result
        with self.assertRaises(ValueError):T.tune(api)
