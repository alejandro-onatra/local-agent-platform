import importlib.util
import io
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


route = load('route_proxy', 'scripts/openhands/route-proxy.py')
stream = load('stream_check', 'scripts/observability/check-stream.py')


class RouteSafetyTests(unittest.TestCase):
    def profile(self):
        return {'api_key_set': True, 'config': {'base_url': 'http://litellm:4000/v1',
                'model': 'openai/qwen3:8b', 'api_key': 'sk-'+'a'*64, 'temperature': 0}}

    def test_rejects_other_endpoint_before_forwarding_credentials(self):
        for url in ('http://ollama:11434/v1', 'http://example.com/v1', 'http://litellm:4000/v1?redirect=1'):
            data = self.profile()
            data['config']['base_url'] = url
            with self.assertRaises(RuntimeError): route.profile_llm(data)

    def test_rejects_missing_or_masked_key(self):
        for key in (None, '**********', 'local-only'):
            data = self.profile()
            data['config']['api_key'] = key
            with self.assertRaises(RuntimeError): route.profile_llm(data)

    def test_rejects_running_or_unknown_state(self):
        for state in ('running', 'waiting_for_confirmation', 'deleting', None):
            with self.assertRaises(RuntimeError): route.ensure_idle({'execution_status': state})
        route.ensure_idle({'execution_status': 'finished'})

    def test_new_usage_id_avoids_old_registry_entry(self):
        source = self.profile()
        a, b = route.profile_llm(source), route.profile_llm(source)
        self.assertNotEqual(a['usage_id'], b['usage_id'])
        self.assertTrue(a['stream'])
        self.assertNotIn('usage_id', source['config'])


class StreamingUsageTests(unittest.TestCase):
    def response(self, records):
        return io.BytesIO(('\n\n'.join('data: '+r for r in records)+'\n').encode())

    def test_reads_final_usage_without_counting_generated_text(self):
        reply = self.response(['{"choices":[{"delta":{"content":"synthetic secret marker"}}]}',
                               '{"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":3}}', '[DONE]'])
        self.assertEqual(stream.read_usage(reply), {'prompt_tokens': 12, 'completion_tokens': 3})

    def test_missing_usage_is_not_zero(self):
        with self.assertRaises(RuntimeError): stream.read_usage(self.response(['{"choices":[]}', '[DONE]']))

    def test_truncated_stream_fails_even_with_usage(self):
        with self.assertRaises(RuntimeError):
            stream.read_usage(self.response(['{"usage":{"prompt_tokens":12,"completion_tokens":3}}']))

    def test_invalid_counts_are_rejected(self):
        for value in ('12', -1, True, 0):
            import json
            record = json.dumps({'usage': {'prompt_tokens': value, 'completion_tokens': 3}})
            with self.assertRaises(RuntimeError): stream.read_usage(self.response([record, '[DONE]']))
