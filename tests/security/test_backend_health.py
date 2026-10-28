"""Regress backend failure hidden by an available frontend and secret-safe output."""
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('backend_health', ROOT / 'scripts/openhands/check-backend.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackendHealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.key = Path(temp.name) / 'key.txt'
        self.key.write_text('synthetic-session-secret')
        headers = Message()
        headers['Content-Type'] = 'application/json'
        self.response = Mock(status=200, headers=headers)
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)

    def test_authenticated_backend_and_proxy_pass_without_reading_settings(self):
        opener = Mock()
        opener.open.return_value = self.response
        result = module.check(self.key, opener, attempts=1)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(opener.open.call_count, 2)
        self.response.read.assert_not_called()
        for call in opener.open.call_args_list:
            self.assertEqual(call.args[0].get_header('X-session-api-key'), 'synthetic-session-secret')
        self.assertNotIn('synthetic-session-secret', json.dumps(result))

    def test_failed_backend_and_502_proxy_do_not_pass_frontend_readiness(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.URLError('sensitive detail'),
                                  urllib.error.HTTPError('url', 502, 'private body', {}, None)] * 3
        sleep = Mock()
        result = module.check(self.key, opener, attempts=3, sleep=sleep)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['checks'], {'agent_server': 'unreachable', 'canvas_proxy': 'upstream_unavailable'})
        self.assertEqual(sleep.call_count, 2)
        self.assertNotIn('sensitive', json.dumps(result))
        self.assertNotIn('private', json.dumps(result))

    def test_auth_failure_stops_without_retry_or_printing_http_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('url', 401, 'private key', {}, None)
        sleep = Mock()
        result = module.check(self.key, opener, sleep=sleep)
        self.assertEqual(result['checks']['agent_server'], 'authentication_rejected')
        sleep.assert_not_called()
        self.assertNotIn('private key', json.dumps(result))

    def test_html_200_is_not_backend_health(self):
        self.response.headers.replace_header('Content-Type', 'text/html')
        opener = Mock()
        opener.open.return_value = self.response
        self.assertEqual(module.check(self.key, opener, attempts=1)['status'], 'failed')

    def test_missing_key_never_contacts_backend(self):
        self.key.unlink()
        opener = Mock()
        result = module.check(self.key, opener)
        self.assertEqual(result['error'], 'session_key_unavailable')
        opener.open.assert_not_called()

    def test_logs_only_emit_fixed_categories_without_sensitive_lines(self):
        result = module.summarize_logs(io.StringIO("secret-prompt-123 [Errno 30] Read-only file system: '/private-name'\nTraceback (most recent call last):\n"))
        self.assertTrue(result['log_indicators']['readonly_filesystem'])
        self.assertTrue(result['log_indicators']['python_traceback'])
        self.assertFalse(result['log_indicators']['storage_full'])
        self.assertNotIn('secret-prompt-123', json.dumps(result))
        self.assertNotIn('private-name', json.dumps(result))

    def test_native_loader_errors_are_detected_without_echoing_raw_text(self):
        text="[PYI-123:ERROR] Failed to extract private-name: decompression resulted in return code -1!\nFailed to load Python shared library: failed to map segment from shared object\n"
        result=module.summarize_logs(io.StringIO(text))
        for key in ['pyinstaller_loader_error','binary_extraction_failed','library_mapping_denied']:
            self.assertTrue(result['log_indicators'][key])
        self.assertNotIn('private-name',json.dumps(result))

    def test_readonly_paths_are_classified_without_disclosing_names(self):
        result=module.summarize_logs(io.StringIO("OSError: [Errno 30] Read-only file system: '/home/openhands/.config/private-family-name'\n"))
        self.assertEqual(result['readonly_path_categories'],['unmounted_home_config'])
        self.assertNotIn('private-family-name',json.dumps(result))
        self.assertNotIn('/home/openhands',json.dumps(result))

    def test_json_escaped_path_and_traceback_frame_do_not_expose_or_misclassify(self):
        text='Traceback: File "/usr/local/lib/private.py"\nOSError: [Errno 30] Read-only file system: "/home/openhands/.openhands/private-name"'
        escaped=json.dumps({'message':text})
        result=module.summarize_logs(io.StringIO(escaped))
        self.assertEqual(result['readonly_path_categories'],['persistent_state'])
        self.assertNotIn('private-name',json.dumps(result))

    def test_unknown_path_stays_unknown_and_no_error_has_empty_categories(self):
        self.assertEqual(module.readonly_locations("[Errno 30] Read-only file system: '/unclassified/private'"),['other_or_unknown'])
        self.assertEqual(module.readonly_locations('Read-only file system'),['other_or_unknown'])
        self.assertEqual(module.readonly_locations('Frontend healthy'),[])
        self.assertEqual(module.readonly_locations("[Errno 30] Read-only file system: '/home/openhands/.config-other/private'"),['other_home_path'])


    def test_cache_usage_error_is_classified_without_private_payload(self):
        text="private-prompt AttributeError: 'PromptTokensDetailsWrapper' object has no attribute 'cache_creation_tokens'"
        report=module.summarize_logs(io.StringIO(text))
        self.assertTrue(report['log_indicators']['cache_usage_attribute_error'])
        self.assertNotIn('private-prompt',json.dumps(report))
        self.assertFalse(module.summarize_logs(io.StringIO('healthy'))['log_indicators']['cache_usage_attribute_error'])


if __name__ == '__main__':
    unittest.main()
