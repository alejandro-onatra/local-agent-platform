"""Fixed log classification, redaction and container identity guards."""
import importlib.util,json,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('identity_logs_test',ROOT/'scripts/identity/log-diagnostics.py')
L=importlib.util.module_from_spec(s);s.loader.exec_module(L)
class LogDiagnosticTests(unittest.TestCase):
    def run_probe(self,raw,labels_ok=True):
        calls=[]
        def run(args):
            calls.append(args)
            if 'inspect' in args:
                service='server' if args[-1].endswith('-server-1') else 'worker'
                body=json.dumps({'com.docker.compose.project':L.PROJECT if labels_ok else 'foreign','com.docker.compose.service':service}).encode()
            else:body=raw
            return SimpleNamespace(stdout=body,returncode=0)
        return L.collect(run),calls
    def test_classifies_failure_without_returning_private_text(self):
        result,calls=self.run_probe(b'PolicyException PRIVATE password secret@example.invalid itoken=PRIVATE Traceback (most recent call last)')
        for service in ('server','worker'):
            self.assertTrue(result['services'][service]['indicators']['policy_exception'])
            self.assertTrue(result['services'][service]['indicators']['traceback'])
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('example.invalid',json.dumps(result))
        self.assertTrue(all('15m' in call and '200' in call for call in calls if 'logs' in call))
    def test_wrong_container_identity_is_never_read(self):
        result,calls=self.run_probe(b'PRIVATE',False)
        self.assertTrue(all('logs' not in call for call in calls))
        self.assertEqual(result['services']['server']['status'],'identity_check_failed')
    def test_quiet_logs_are_not_reported_as_proof_of_success(self):
        result,_=self.run_probe(b'')
        self.assertEqual(result['status'],'collected')
        self.assertFalse(any(result['services']['server']['indicators'].values()))
    def test_probe_exceptions_never_leak(self):
        def run(args):raise RuntimeError('PRIVATE details')
        result=L.collect(run)
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual(result['services']['server']['status'],'probe_unavailable')
    def test_large_log_output_is_marked_truncated(self):
        result,_=self.run_probe(b'x'*1048577)
        self.assertTrue(result['services']['server']['truncated'])
if __name__=='__main__':unittest.main()


class StructuredFailureTests(unittest.TestCase):
    def test_authorization_error_aggregates_without_leaking_state_or_body(self):
        line={'event':'/api/v3/flows/executor/family-authorize/?state=PRIVATE-STATE',
              'status':400,'body':'PRIVATE-OTP','user':'PRIVATE-USER'}
        raw=(json.dumps(line)+'\n'+json.dumps(line)).encode()
        result=L.structured_failures(raw)
        self.assertEqual(result['http_failures'],[{'route':'authorization_flow','status':400,'count':2}])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_native_routes_and_supported_status_fields(self):
        rows=[{'path':'/api/v3/flows/executor/family-login/','status_code':403},
              {'request_path':'/application/o/token/','http_status':'500'},
              {'event':'POST /outpost.goauthentik.io/callback?code=PRIVATE HTTP/1.1','status':502}]
        result=L.structured_failures(('\n'.join(map(json.dumps,rows))).encode())
        self.assertEqual({(x['route'],x['status']) for x in result['http_failures']},
                         {('login_flow',403),('oauth_token',500),('proxy_callback',502)})
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_unknown_routes_are_reduced_to_fixed_other(self):
        result=L.structured_failures(json.dumps({'event':'/PRIVATE-PATH?password=PRIVATE','status':401}).encode())
        self.assertEqual(result['http_failures'],[{'route':'other','status':401,'count':1}])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_malformed_or_success_lines_do_not_fabricate_failures(self):
        rows=[[],None,{'status':True},{'status':[]},{'status':{'PRIVATE':500}},
              {'status':'PRIVATE'},{'status':200},{'status':302},{'status':999},
              {'status':400,'path':'http://['}]
        raw=b'not json PRIVATE\n'+b'\n'.join(json.dumps(x).encode() for x in rows)
        result=L.structured_failures(raw)
        self.assertEqual(result['http_failures'],[{'route':'other','status':400,'count':1}])
        self.assertFalse(result['structured_error_seen'])

    def test_error_level_is_reported_without_exposing_exception_text(self):
        result=L.structured_failures(b'{"level":"ERROR","error":"PRIVATE unexpected failure"}')
        self.assertTrue(result['structured_error_seen']);self.assertEqual(result['http_failures'],[])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_collect_exposes_summary_but_never_raw_payload(self):
        result,_=LogDiagnosticTests().run_probe(b'{"event":"/api/v3/flows/executor/family-authorize/?state=PRIVATE","status":500,"level":"error"}')
        server=result['services']['server']
        self.assertTrue(server['structured_error_seen'])
        self.assertEqual(server['http_failures'][0]['route'],'authorization_flow')
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_additional_markers_are_only_indicators(self):
        result,_=LogDiagnosticTests().run_probe(b'x509: PRIVATE certificate signed by unknown authority; oauth2: PRIVATE; invalid TOTP')
        for service in ('server','worker'):
            flags=result['services'][service]['indicators']
            self.assertTrue(flags['tls_certificate_error']);self.assertTrue(flags['oauth_exchange_error'])
            self.assertTrue(flags['totp_rejected'])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_native_outpost_callback_failures_are_detected_and_redacted(self):
        result,_=LogDiagnosticTests().run_probe(b'failed to redeem code PRIVATE-CODE; failed to save session PRIVATE-COOKIE; invalid state PRIVATE-STATE')
        flags=result['services']['server']['indicators']
        self.assertTrue(flags['oauth_exchange_error']);self.assertTrue(flags['callback_session_error'])
        self.assertNotIn('PRIVATE',json.dumps(result))
