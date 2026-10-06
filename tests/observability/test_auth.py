import contextlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts/observability'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

secrets = module('prepare', 'prepare-secrets.py')
checks = module('checks', 'check-stack.py')

class AuthenticationChecks(unittest.TestCase):
    def test_credentials_are_private_distinct_and_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'private'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                secrets.prepare(folder)
            grafana = (folder/'admin-password').read_text()
            key = (folder/'litellm-master-key').read_text()
            self.assertRegex(key.strip(), r'^sk-[a-f0-9]{64}$')
            self.assertNotEqual(grafana, key)
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            for name in ['admin-password','litellm-master-key']:
                self.assertEqual(stat.S_IMODE((folder/name).stat().st_mode), 0o600)
            secrets.prepare(folder)
            self.assertEqual((folder/'admin-password').read_text(), grafana)
            self.assertEqual((folder/'litellm-master-key').read_text(), key)
            self.assertNotIn(key.strip(), output.getvalue())

    def test_invalid_existing_key_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            secrets.prepare(folder)
            (folder/'litellm-master-key').write_text('weak-key')
            with self.assertRaises(ValueError): secrets.prepare(folder)
            self.assertEqual((folder/'litellm-master-key').read_text(), 'weak-key')

    def test_symlink_credential_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'private'
            folder.mkdir()
            target = Path(tmp)/'unrelated'
            target.write_text('unchanged')
            (folder/'litellm-master-key').symlink_to(target)
            with self.assertRaises(OSError): secrets.prepare(folder)
            self.assertEqual(target.read_text(), 'unchanged')

    def test_token_is_only_sent_to_proxy(self):
        with patch.object(checks.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            checks.request('http://litellm:4000/v1/models', token='synthetic-test-key')
            self.assertEqual(send.call_args.args[0].get_header('Authorization'), 'Bearer synthetic-test-key')
        with patch.object(checks.urllib.request, 'urlopen') as send:
            with self.assertRaises(ValueError):
                checks.request('http://tempo:3200/ready', token='synthetic-test-key')
            send.assert_not_called()

    def test_backend_request_omits_proxy_credential(self):
        with patch.object(checks.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            checks.request('http://collector:4318/v1/logs', {})
            self.assertIsNone(send.call_args.args[0].get_header('Authorization'))

    def test_native_trace_requires_matching_resource_and_entry_span(self):
        native = {'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'litellm-proxy'}}]},'scopeSpans':[{'spans':[{'name':'Received Proxy Server Request'}]}]}]}
        self.assertTrue(checks.model_trace_valid(native))
        native['resourceSpans'][0]['resource']['attributes'][0]['value']['stringValue'] = 'observability-smoke'
        self.assertFalse(checks.model_trace_valid(native))
        native['resourceSpans'][0]['resource']['attributes'][0]['value']['stringValue'] = 'litellm-proxy'
        native['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['name'] = 'operation'
        self.assertFalse(checks.model_trace_valid(native))

    def test_trace_context_is_valid_and_sent_only_to_proxy(self):
        traceparent = '00-'+'a'*32+'-'+'b'*16+'-01'
        with patch.object(checks.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            checks.request('http://litellm:4000/v1/chat/completions', {}, traceparent=traceparent)
            self.assertEqual(send.call_args.args[0].get_header('Traceparent'), traceparent)
        with patch.object(checks.urllib.request, 'urlopen') as send:
            for url, parent in [('http://tempo:3200/ready', traceparent), ('http://litellm:4000/v1/models','invalid')]:
                with self.assertRaises(ValueError): checks.request(url, traceparent=parent)
            send.assert_not_called()
