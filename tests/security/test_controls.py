"""Regression checks against real source copies and bounded synthetic TLS peers."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('sec_controls', ROOT / 'scripts/security/check-controls.py')
SEC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEC)


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sec-control-test-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        for name in (*SEC.SOURCES, 'config/security/controls.yaml', 'scripts/security/check-controls.py'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def mutate(self, filename, change):
        path = self.repo / filename
        doc = yaml.safe_load(path.read_text())
        change(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))

    def agent(self, change):
        self.mutate(SEC.SOURCES[1], lambda d: change(d['services']['openhands']))

    def failed(self, probe):
        self.assertEqual(SEC.source_checks(self.repo)[probe]['status'], 'failed')

    def test_clean_source_does_not_certify_any_sec_control(self):
        report = SEC.evaluate(self.repo)
        self.assertEqual(report['config_guard'], 'passed')
        self.assertEqual(report['totals'], {'passed': 0, 'failed': 0, 'pending': 15})
        self.assertEqual(SEC.exit_code(report, 'config'), 0)
        self.assertEqual(SEC.exit_code(report, 'readiness'), 2)

    def test_wildcard_and_unspecified_ports_block(self):
        for port in ['8000:8080', '0.0.0.0:8000:8080', '[::]:8000:8080',
                     {'target': 8080, 'published': '8000'},
                     {'target': 8080, 'host_ip': '192.168.1.20'}]:
            with self.subTest(port_type=type(port).__name__):
                self.mutate(SEC.SOURCES[1], lambda d: d['services']['openhands-proxy'].update(ports=[port]))
                self.failed('compose.loopback')

    def test_ipv6_loopback_and_long_syntax_are_supported(self):
        for port in ['[::1]:8000:8080', {'target': 8080, 'published': '8000', 'host_ip': '127.0.0.1'}]:
            self.assertTrue(SEC.loopback_port(port))

    def test_privilege_and_host_namespace_regressions_block(self):
        cases = [{'privileged': True}, {'cap_add': ['SYS_ADMIN']}, {'pid': 'host'},
                 {'ipc': 'host'}, {'network_mode': 'host'}, {'use_api_socket': True},
                 {'user': '0:0'}, {'security_opt': ['seccomp=unconfined']}, {'cap_drop': []}]
        original = yaml.safe_load((self.repo / SEC.SOURCES[1]).read_text())
        for mutation in cases:
            with self.subTest(field=next(iter(mutation))):
                (self.repo / SEC.SOURCES[1]).write_text(yaml.safe_dump(original, sort_keys=False))
                self.agent(lambda s: s.update(mutation))
                probes = SEC.source_checks(self.repo)
                self.assertTrue(any(probes[p]['status'] == 'failed' for p in SEC.GUARDS))

    def test_socket_and_personal_mounts_block(self):
        for source, target in [('/var/run/docker.sock', '/run/docker.sock'),
                               ('/home/person/.ssh', '/projects'), ('/', '/host'),
                               ('/safe/root_ca_key', '/secrets/root_ca_key')]:
            self.agent(lambda s: s.update(volumes=[{'type': 'bind', 'source': source, 'target': target}]))
            self.failed('compose.mounts')

    def test_agent_external_network_blocks(self):
        self.agent(lambda s: s.update(networks=['default', 'agent-link']))
        self.failed('compose.agent_network')

    def test_internal_network_flag_removal_blocks(self):
        self.mutate(SEC.SOURCES[1], lambda d: d['networks']['agent-link'].update(internal=False))
        self.failed('compose.agent_network')

    def test_unbounded_resources_block(self):
        original = yaml.safe_load((self.repo / SEC.SOURCES[1]).read_text())
        for mutation in [{'mem_limit': '0'}, {'cpus': 0}, {'pids_limit': -1},
                         {'logging': {'driver': 'json-file', 'options': {}}}]:
            (self.repo / SEC.SOURCES[1]).write_text(yaml.safe_dump(original, sort_keys=False))
            self.agent(lambda s: s.update(mutation))
            self.failed('compose.resources')

    def test_override_fragment_cannot_remove_hardening_or_limits(self):
        original = yaml.safe_load((self.repo / SEC.SOURCES[1]).read_text())
        for field, value, probe in [('cap_drop', [], 'compose.hardening'),
                                    ('security_opt', [], 'compose.hardening'),
                                    ('cpus', 0, 'compose.resources'),
                                    ('mem_limit', '0', 'compose.resources')]:
            with self.subTest(field=field):
                (self.repo / SEC.SOURCES[1]).write_text(yaml.safe_dump(original, sort_keys=False))
                self.mutate(SEC.SOURCES[1], lambda d: d['services']['ollama'].update({field: value}))
                self.failed(probe)

    def test_unknown_incomplete_service_is_rejected(self):
        self.mutate(SEC.SOURCES[1], lambda d: d['services'].update(unknown={'ports': []}))
        with self.assertRaises(SEC.InvalidConfig):
            SEC.source_checks(self.repo)

    def test_report_parent_symlink_is_rejected(self):
        (self.repo / 'artifacts').symlink_to(Path(self.temp.name))
        with self.assertRaises(SEC.InvalidConfig):
            SEC.write_report(self.repo, {})

    def test_hardening_candidate_cannot_remove_readonly_or_temporary_bounds(self):
        original = yaml.safe_load((self.repo / SEC.SOURCES[3]).read_text())
        for mutation in [{'read_only':False},{'user':'root'},{'tmpfs':['/tmp:rw']},
                         {'security_opt':['no-new-privileges:true','apparmor:unconfined']}]:
            (self.repo / SEC.SOURCES[3]).write_text(yaml.safe_dump(original,sort_keys=False))
            self.mutate(SEC.SOURCES[3],lambda d:d['services']['openhands'].update(mutation))
            self.failed('compose.hardening_candidate')

    def test_config_tmpfs_cannot_be_executable_unbounded_or_world_writable(self):
        original = yaml.safe_load((self.repo / SEC.SOURCES[3]).read_text())
        entry = original['services']['openhands']['tmpfs'][-1]
        for unsafe in [entry.replace('noexec,',''),entry.replace('size=64m,',''),
                       entry.replace('mode=0700','mode=0777'),entry.replace('/.config:', '/.ssh:')]:
            with self.subTest(unsafe_option=unsafe):
                (self.repo / SEC.SOURCES[3]).write_text(yaml.safe_dump(original,sort_keys=False))
                self.mutate(SEC.SOURCES[3],lambda d:d['services']['openhands']['tmpfs'].__setitem__(-1,unsafe))
                self.failed('compose.hardening_candidate')

    def test_backend_launcher_mount_is_exact_and_readonly(self):
        original = yaml.safe_load((self.repo / SEC.SOURCES[3]).read_text())
        for field, value in [('read_only', False), ('source', '/home/person/.ssh'),
                             ('target', '/usr/local/bin/python')]:
            with self.subTest(field=field):
                (self.repo / SEC.SOURCES[3]).write_text(yaml.safe_dump(original, sort_keys=False))
                self.mutate(SEC.SOURCES[3], lambda d: d['services']['openhands']['volumes'][0].update({field:value}))
                self.failed('compose.hardening_candidate')

    def test_mutable_image_blocks(self):
        self.agent(lambda s: s.update(image='example.invalid/agent:latest'))
        self.failed('compose.digests')

    def test_literal_credentials_fail_without_echo(self):
        marker = 'synthetic-value-never-echo-this'
        self.agent(lambda s: s['environment'].update(PASSWORD=marker))
        report = SEC.evaluate(self.repo)
        self.assertEqual(report['config_guard'], 'failed')
        self.assertEqual(SEC.exit_code(report, 'readiness'), 1)
        self.assertNotIn(marker, json.dumps(report))

    def test_secret_environment_literal_default_is_forbidden(self):
        self.agent(lambda s: s['environment'].update(PASSWORD='${PASSWORD:-synthetic-default}'))
        self.failed('compose.secret_delivery')

    def test_secret_scanner_unavailable_cannot_pass(self):
        result = SEC.secret_check(self.repo)
        self.assertEqual(result['status'], 'failed')

    def test_root_key_reference_in_environment_is_forbidden(self):
        self.agent(lambda s: s['environment'].update(ROOT_CA_PRIVATE_KEY='${PRIVATE_FILE}'))
        self.failed('compose.secret_delivery')

    def test_missing_source_and_symlink_are_rejected(self):
        path = self.repo / SEC.SOURCES[0]
        path.unlink()
        with self.assertRaises(SEC.InvalidConfig):
            SEC.source_checks(self.repo)
        path.symlink_to(ROOT / SEC.SOURCES[0])
        with self.assertRaises(SEC.InvalidConfig):
            SEC.source_checks(self.repo)

    def test_duplicate_yaml_keys_fail_closed(self):
        (self.repo / SEC.SOURCES[0]).write_text('services: {}\nservices: {}\n')
        with self.assertRaises(SEC.InvalidConfig):
            SEC.source_checks(self.repo)

    def test_missing_sec_control_fails_closed(self):
        self.mutate('config/security/controls.yaml', lambda d: d['controls'].pop('SEC-04'))
        with self.assertRaises(SEC.InvalidConfig):
            SEC.load_matrix(self.repo)

    def test_removed_guard_mapping_fails_closed(self):
        self.mutate('config/security/controls.yaml',
                    lambda d: d['controls']['SEC-12'].update(required=['live.scan']))
        with self.assertRaises(SEC.InvalidConfig):
            SEC.load_matrix(self.repo)

    def test_failure_takes_precedence_over_missing_evidence(self):
        self.agent(lambda s: s.update(privileged=True))
        report = SEC.evaluate(self.repo)
        self.assertEqual(report['readiness'], 'failed')
        self.assertGreater(report['totals']['failed'], 0)
        self.assertGreater(report['totals']['pending'], 0)

    def test_pending_probe_cannot_be_turned_into_a_pass_by_empty_object(self):
        controls = SEC.load_matrix(self.repo)
        rows, counts = SEC.summarize(controls, {})
        self.assertEqual(counts['pending'], 15)
        self.assertEqual(counts['passed'], 0)

    def test_report_is_private_and_in_excluded_artifacts(self):
        path = SEC.write_report(self.repo, SEC.evaluate(self.repo))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent, self.repo / 'artifacts/security')

    def test_cli_no_network_and_pending_exit(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('SEC_CA_')}
        process = subprocess.run([sys.executable, str(self.repo / 'scripts/security/check-controls.py')],
                                 env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 2)
        report = json.loads(process.stdout.split('\nReport:', 1)[0])
        self.assertEqual(report['totals']['pending'], 15)

    def test_cli_malformed_config_withholds_source_values(self):
        marker = 'synthetic-sensitive-diagnostic-text'
        (self.repo / SEC.SOURCES[0]).write_text('services: [' + marker)
        process = subprocess.run([sys.executable, str(self.repo / 'scripts/security/check-controls.py')],
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 1)
        self.assertNotIn(marker, process.stdout + process.stderr)


class TLSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sec-tls-test-')
        self.addCleanup(self.temp.cleanup)
        self.cert = Path(self.temp.name) / 'public.crt'
        # Format fixture only: transport/context is mocked, no private key is generated.
        self.cert.write_text(ssl.DER_cert_to_PEM_cert(b'synthetic-public-der'))
        self.fingerprint = hashlib.sha256(b'synthetic-public-der').hexdigest()
        self.connect = MagicMock()
        self.factory = MagicMock()
        self.ctx = self.factory.return_value
        self.stream = self.ctx.wrap_socket.return_value.__enter__.return_value
        expiry = datetime.now(timezone.utc) + timedelta(days=20)
        self.stream.getpeercert.return_value = {'notAfter': expiry.strftime('%b %d %H:%M:%S %Y GMT')}

    def test_no_explicit_request_does_not_connect(self):
        result = SEC.tls_checks(connect=self.connect, context_factory=self.factory)
        self.assertEqual(result['tls.portal']['status'], 'pending')
        self.connect.assert_not_called()

    def test_wrong_fingerprint_does_not_connect(self):
        result = SEC.tls_checks(self.cert, '0' * 64, self.connect, self.factory)
        self.assertEqual(result['tls.root_fingerprint']['status'], 'failed')
        self.connect.assert_not_called()

    def test_verified_probe_forces_hostname_and_chain_validation(self):
        result = SEC.tls_checks(self.cert, self.fingerprint, self.connect, self.factory)
        self.assertEqual(result['tls.portal']['status'], 'passed')
        self.assertTrue(self.ctx.check_hostname)
        self.assertEqual(self.ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(self.ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.connect.assert_called_once_with(('portal.home.arpa', 443), timeout=5)
        self.ctx.wrap_socket.assert_called_once()
        self.assertEqual(self.ctx.wrap_socket.call_args.kwargs['server_hostname'], 'portal.home.arpa')

    def test_short_expiry_fails(self):
        expiry = datetime.now(timezone.utc) + timedelta(days=1)
        self.stream.getpeercert.return_value = {'notAfter': expiry.strftime('%b %d %H:%M:%S %Y GMT')}
        result = SEC.tls_checks(self.cert, self.fingerprint, self.connect, self.factory)
        self.assertEqual(result['tls.portal']['status'], 'failed')

    def test_certificate_error_does_not_leak_exception(self):
        self.factory.side_effect = ssl.SSLCertVerificationError('synthetic-private-diagnostic')
        result = SEC.tls_checks(self.cert, self.fingerprint, self.connect, self.factory)
        self.assertEqual(result['tls.portal']['status'], 'failed')
        self.assertEqual(result['tls.root_fingerprint']['status'], 'passed')
        self.assertNotIn('synthetic-private-diagnostic', json.dumps(result))

    def test_non_certificate_material_rejected_before_connection(self):
        self.cert.write_text('not a certificate')
        result = SEC.tls_checks(self.cert, self.fingerprint, self.connect, self.factory)
        self.assertEqual(result['tls.portal']['status'], 'failed')
        self.connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
