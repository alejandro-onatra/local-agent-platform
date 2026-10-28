#!/usr/bin/env python3
"""Fail-closed source guards and honest SEC readiness; never deploy services."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import tempfile
import time

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ('infra/llm/compose.yaml', 'infra/openhands/compose.yaml',
           'infra/observability/compose.yaml', 'infra/openhands/hardening.yaml')
GUARDS = ('compose.loopback', 'compose.hardening', 'compose.mounts',
          'compose.agent_network', 'compose.resources', 'compose.digests',
          'compose.secret_delivery', 'compose.hardening_candidate')
STATES = {'passed', 'failed', 'pending'}


class InvalidConfig(ValueError):
    """Errors are intentionally reported without source values."""


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise InvalidConfig('Duplicate or non-string mapping key')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise InvalidConfig('Missing, linked or oversized input')
    value = yaml.load(path.read_text(), Loader=UniqueLoader)
    if not isinstance(value, dict):
        raise InvalidConfig('Expected mapping')
    return value


def result(status, reason):
    if status not in STATES:
        raise InvalidConfig('Unknown result state')
    return {'status': status, 'reason': reason}


def guard(ok):
    return result('passed' if ok else 'failed',
                  'source_condition_satisfied' if ok else 'source_condition_violated')


def loopback_port(port):
    if isinstance(port, dict):
        host = port.get('host_ip')
    elif isinstance(port, str):
        # Short syntax requires an explicit IP, including bracketed IPv6.
        match = re.fullmatch(r'(\[[^\]]+\]|[^:]+):\d+(?:-\d+)?:\d+(?:-\d+)?(?:/(?:tcp|udp))?', port)
        host = match.group(1).strip('[]') if match else None
    else:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def mounts(service):
    items = service.get('volumes', [])
    if not isinstance(items, list):
        raise InvalidConfig('Invalid mounts')
    parsed = []
    for item in items:
        if isinstance(item, dict):
            if item.get('type') not in {'bind', 'volume'}:
                raise InvalidConfig('Unsupported mount type')
            source, target = item.get('source', ''), item.get('target', '')
            bind = item['type'] == 'bind'
        elif isinstance(item, str):
            parts = item.rsplit(':', 1)
            if len(parts) == 2 and parts[-1] in {'ro', 'rw', 'ro,z', 'rw,z'}:
                parts = parts[0].rsplit(':', 1)
            if len(parts) != 2:
                raise InvalidConfig('Unsupported mount syntax')
            source, target = parts
            bind = source.startswith(('/', '.', '~', '${'))
        else:
            raise InvalidConfig('Invalid mount')
        if not isinstance(source, str) or not isinstance(target, str) or not target.startswith('/'):
            raise InvalidConfig('Invalid mount fields')
        parsed.append((source, target, bind))
    return parsed


def positive(value):
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError):
        return False


def positive_memory(value):
    if isinstance(value, (int, float)):
        return positive(value)
    return isinstance(value, str) and bool(re.fullmatch(r'[1-9]\d*(?:\.\d+)?[bkmgBKMG]?', value))


def environment(service):
    env = service.get('environment', {})
    if isinstance(env, dict):
        return env
    if isinstance(env, list) and all(isinstance(item, str) and '=' in item for item in env):
        pairs = [item.split('=', 1) for item in env]
        if len({pair[0] for pair in pairs}) != len(pairs):
            raise InvalidConfig('Duplicate environment key')
        return dict(pairs)
    raise InvalidConfig('Unsupported environment')


def source_checks(repo):
    docs = [load_yaml(repo / name) for name in SOURCES]
    all_services = []
    full_services = []
    for index, doc in enumerate(docs):
        if doc.get('include') or not isinstance(doc.get('services'), dict) or not doc['services']:
            raise InvalidConfig('Unsupported compose structure')
        for name, service in doc['services'].items():
            if not isinstance(service, dict) or service.get('extends') or service.get('build'):
                raise InvalidConfig('Unsupported service structure')
            if 'image' not in service and (index, name) not in {(1, 'ollama'), (3, 'openhands')}:
                raise InvalidConfig('Unknown incomplete service')
            all_services.append(service)
            if 'image' in service:
                full_services.append(service)
    if not full_services:
        raise InvalidConfig('No image services')
    agent = docs[1]['services'].get('openhands')
    if not isinstance(agent, dict):
        raise InvalidConfig('Missing baseline agent')
    checks = {}
    checks['compose.loopback'] = guard(all(
        isinstance(s.get('ports', []), list) and all(loopback_port(p) for p in s.get('ports', []))
        and not s.get('network_mode') for s in all_services))
    def hardened_fields(s, required=False):
        drops = s.get('cap_drop', [])
        opts = s.get('security_opt', [])
        return (isinstance(drops, list) and isinstance(opts, list) and
                (not required and 'cap_drop' not in s or 'ALL' in drops) and
                (not required and 'security_opt' not in s or 'no-new-privileges:true' in opts) and
                not any(str(opt).startswith(('seccomp=unconfined', 'apparmor=unconfined')) for opt in opts))
    checks['compose.hardening'] = guard(all(
        s.get('privileged', False) is False and not s.get('cap_add') and
        not s.get('use_api_socket') and not s.get('volumes_from') and
        not s.get('devices') and not s.get('device_cgroup_rules') and
        not any(s.get(k) for k in ('pid', 'ipc', 'uts', 'userns_mode', 'cgroup'))
        for s in all_services) and all(hardened_fields(s) for s in all_services) and
        all(hardened_fields(s, required=True) for s in full_services) and
        str(agent.get('user', 'image_default')).split(':', 1)[0] not in {'0', 'root'})
    parsed = [mounts(s) for s in all_services]
    management = re.compile(r'(?:docker|podman|containerd)\.sock|(?:root[-_]ca|ca[-_]root).*key', re.I)
    safe_mounts = all(not management.search(source + ' ' + target)
                      for values in parsed for source, target, _ in values)
    allowed_agent = {
        ('openhands-state', '/home/openhands/.openhands', False),
        ('${OH_WORKSPACE:?Run scripts/openhands/up.sh}', '/projects', True),
    }
    checks['compose.mounts'] = guard(safe_mounts and set(mounts(agent)) == allowed_agent)
    checks['compose.agent_network'] = guard(
        agent.get('networks') == ['agent-link'] and not agent.get('ports') and
        docs[1].get('networks', {}).get('agent-link', {}).get('internal') is True)
    def bounded_logging(logging):
        if not isinstance(logging, dict) or not isinstance(logging.get('options'), dict):
            return False
        options = logging['options']
        return (logging.get('driver') == 'json-file' and
                positive_memory(options.get('max-size')) and positive(options.get('max-file')))
    def bounded_fields(s, required=False):
        return ((not required and 'cpus' not in s or positive(s.get('cpus'))) and
                (not required and 'mem_limit' not in s or positive_memory(s.get('mem_limit'))) and
                ('pids_limit' not in s or positive(s['pids_limit'])) and
                (not required and 'logging' not in s or bounded_logging(s.get('logging'))))
    checks['compose.resources'] = guard(all(bounded_fields(s) for s in all_services) and
                                       all(bounded_fields(s, required=True) for s in full_services) and
                                       positive(agent.get('pids_limit')))
    checks['compose.digests'] = guard(all(isinstance(s['image'], str) and
        re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', s['image']) for s in full_services))
    secret_name = re.compile(r'PASSWORD|TOKEN|SECRET|PRIVATE_KEY|MASTER_KEY', re.I)
    secret_delivery = True
    for service in all_services:
        for name, value in environment(service).items():
            if not isinstance(name, str):
                raise InvalidConfig('Invalid environment name')
            if re.search(r'ROOT.*(?:PRIVATE|KEY|PASSWORD)', name, re.I):
                secret_delivery = False
            elif secret_name.search(name):
                # Existing referenced credentials are not literals; their transport
                # still needs migration/host evidence under SEC-09.
                secret_delivery &= isinstance(value, str) and bool(re.fullmatch(r'\$\{[A-Z_][A-Z0-9_]*(?::?\?[^{}]*)?\}', value))
    checks['compose.secret_delivery'] = guard(secret_delivery)
    candidate = docs[3]['services'].get('openhands', {})
    checks['compose.hardening_candidate'] = guard(
        set(docs[3]) == {'services'} and set(docs[3]['services']) == {'openhands'} and
        set(candidate) == {'user','init','read_only','security_opt','tmpfs','volumes'} and
        candidate.get('user') == '${OH_ISOLATED_USER:?Set the verified existing image user}' and
        candidate.get('init') is True and candidate.get('read_only') is True and
        candidate.get('security_opt') == ['no-new-privileges:true','apparmor:docker-default'] and
        candidate.get('volumes') == [{
            'type':'bind', 'source':'../../scripts/openhands/start-agent-server.py',
            'target':'/usr/local/bin/openhands-agent-server', 'read_only':True,
            'bind':{'create_host_path':False}}] and
        candidate.get('tmpfs') == [
            '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
            '/home/openhands/workspace:rw,nosuid,nodev,size=512m,mode=0770,uid=${OH_ISOLATED_UID:?Set verified UID},gid=${OH_ISOLATED_GID:?Set verified GID}',
            '/home/openhands/.cache:rw,nosuid,nodev,size=128m,mode=0700,uid=${OH_ISOLATED_UID:?Set verified UID},gid=${OH_ISOLATED_GID:?Set verified GID}',
            '/home/openhands/.config:rw,nosuid,nodev,noexec,size=64m,mode=0700,uid=${OH_ISOLATED_UID:?Set verified UID},gid=${OH_ISOLATED_GID:?Set verified GID}'])
    return checks


def load_matrix(repo):
    matrix = load_yaml(repo / 'config/security/controls.yaml')
    if matrix.get('schema_version') != 1 or matrix.get('portal') != 'portal.home.arpa':
        raise InvalidConfig('Invalid matrix version or portal')
    controls = matrix.get('controls')
    if not isinstance(controls, dict) or list(controls) != [f'SEC-{i:02}' for i in range(1, 16)]:
        raise InvalidConfig('Missing, unordered or extra controls')
    for control in controls.values():
        if set(control) != {'title', 'required'} or not isinstance(control['title'], str):
            raise InvalidConfig('Invalid control schema')
        required = control['required']
        if not isinstance(required, list) or not required or len(set(required)) != len(required):
            raise InvalidConfig('Missing or duplicate requirements')
        if not all(isinstance(p, str) and re.fullmatch(r'[a-z][a-z0-9_.]+', p) for p in required):
            raise InvalidConfig('Invalid probe identifier')
    listed = {p for c in controls.values() for p in c['required']}
    if not set(GUARDS).issubset(listed):
        raise InvalidConfig('Missing source guard coverage')
    return controls


def tls_checks(ca_file=None, fingerprint=None, connect=socket.create_connection,
               context_factory=ssl.create_default_context):
    pending = result('pending', 'trusted_tls_probe_not_requested')
    if ca_file is None or fingerprint is None:
        return {'tls.root_fingerprint': pending, 'tls.portal': pending}
    root = result('failed', 'trusted_tls_probe_failed')
    try:
        path = Path(ca_file)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
            raise ValueError('Invalid public certificate file')
        pem = path.read_text()
        if pem.count('-----BEGIN CERTIFICATE-----') != 1 or 'PRIVATE KEY' in pem:
            raise ValueError('Expected one public certificate')
        der = ssl.PEM_cert_to_DER_cert(pem)
        actual = hashlib.sha256(der).hexdigest()
        expected = fingerprint.replace(':', '').lower()
        if not re.fullmatch(r'[0-9a-f]{64}', expected) or actual != expected:
            return {'tls.root_fingerprint': result('failed', 'root_fingerprint_mismatch'),
                    'tls.portal': result('pending', 'no_connection_without_trusted_root')}
        root = result('passed', 'public_root_fingerprint_matches')
        ctx = context_factory(cafile=str(path))
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        with connect(('portal.home.arpa', 443), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname='portal.home.arpa') as stream:
                remaining = ssl.cert_time_to_seconds(stream.getpeercert()['notAfter']) - time.time()
                portal = guard(remaining >= 7 * 86400)
                portal['reason'] = 'trusted_hostname_chain_and_expiry' if portal['status'] == 'passed' else 'expires_within_seven_days'
        return {'tls.root_fingerprint': root, 'tls.portal': portal}
    except (OSError, ValueError, KeyError, ssl.SSLError):
        return {'tls.root_fingerprint': root,
                'tls.portal': result('failed', 'trusted_tls_probe_failed')}


def secret_check(repo):
    try:
        process = subprocess.run(['bash', 'scripts/security/check-secrets.sh'], cwd=repo,
                                 text=True, capture_output=True, timeout=180, check=False)
        if process.returncode != 0:
            return result('failed', 'secret_gate_failed_or_unavailable')
        report = json.loads(process.stdout.split('\nReport:', 1)[0])
        if report.get('status') != 'passed' or report.get('canary_detection_and_redaction') != 'passed':
            return result('failed', 'secret_gate_evidence_invalid')
        return result('passed', 'existing_redacted_secret_gate_passed')
    except (OSError, ValueError, subprocess.SubprocessError):
        return result('failed', 'secret_gate_failed_or_unavailable')


def summarize(controls, probes):
    rows = []
    for control_id, definition in controls.items():
        evidence = {p: probes.get(p, result('pending', 'probe_not_implemented_or_requires_host_evidence'))
                    for p in definition['required']}
        states = {v['status'] for v in evidence.values()}
        status = 'failed' if 'failed' in states else 'pending' if 'pending' in states else 'passed'
        rows.append({'id': control_id, 'status': status, 'checks': evidence})
    counts = Counter(row['status'] for row in rows)
    return rows, {s: counts[s] for s in ('passed', 'failed', 'pending')}


def evaluate(repo, *, secrets=False, ca_file=None, fingerprint=None):
    controls = load_matrix(repo)
    probes = source_checks(repo)
    probes.update(tls_checks(ca_file, fingerprint))
    probes['secrets.scan'] = secret_check(repo) if secrets else result('pending', 'secret_gate_not_requested')
    rows, counts = summarize(controls, probes)
    hashes = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
              for name in (*SOURCES, 'config/security/controls.yaml', 'scripts/security/check-controls.py')}
    return {'schema_version': 1, 'time_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'Declared source guards plus explicitly requested probes; not deployed SEC certification',
            'source_sha256': hashes, 'config_guard': 'failed' if any(probes[p]['status'] == 'failed' for p in GUARDS) else 'passed',
            'readiness': 'failed' if counts['failed'] else 'pending' if counts['pending'] else 'passed',
            'totals': counts, 'controls': rows}


def exit_code(report, scope):
    if report.get('error') or report['config_guard'] == 'failed':
        return 1
    if scope == 'config':
        return 0
    return {'passed': 0, 'failed': 1, 'pending': 2}[report['readiness']]


def write_report(repo, report):
    directory = repo / 'artifacts/security'
    if directory.is_symlink() or directory.parent.is_symlink():
        raise InvalidConfig('Linked report directory')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', prefix='controls-', suffix='.json',
                                     dir=directory, delete=False) as handle:
        os.chmod(handle.name, 0o600)
        json.dump(report, handle, indent=2)
        handle.write('\n')
        return Path(handle.name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('config', 'readiness'), default='readiness')
    parser.add_argument('--secrets', action='store_true', help='Run the existing redacted Gitleaks gate')
    parser.add_argument('--tls', action='store_true', help='Connect only to portal.home.arpa:443')
    args = parser.parse_args(argv)
    if args.scope == 'config' and (args.tls or args.secrets):
        parser.error('config scope only runs offline source guards')
    # Public certificate location/fingerprint are configuration, never private keys.
    ca_file = os.environ.get('SEC_CA_CERT') if args.tls else None
    fingerprint = os.environ.get('SEC_CA_SHA256') if args.tls else None
    if args.tls and (not ca_file or not fingerprint):
        parser.error('--tls requires SEC_CA_CERT and SEC_CA_SHA256 (public material only)')
    os.umask(0o077)
    try:
        report = evaluate(ROOT, secrets=args.secrets, ca_file=ca_file, fingerprint=fingerprint)
    except Exception:
        # Fail closed at the CLI boundary without exposing parser/source details.
        report = {'schema_version': 1, 'config_guard': 'failed', 'readiness': 'failed',
                  'error': 'input_invalid_or_unavailable; sensitive details withheld'}
    try:
        path = write_report(ROOT, report)
    except (OSError, InvalidConfig):
        print('Security report could not be saved; details withheld.')
        return 1
    summary = {k: report[k] for k in ('config_guard', 'readiness', 'totals', 'error') if k in report}
    summary['failed_checks'] = sorted({p for row in report.get('controls', [])
                                      for p, value in row['checks'].items() if value['status'] == 'failed'})
    print(json.dumps(summary, indent=2))
    print(f'Report: {path}')
    return exit_code(report, args.scope)


if __name__ == '__main__':
    raise SystemExit(main())
