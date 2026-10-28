#!/usr/bin/env python3
"""Inspect only selected Docker fields and numeric process controls; never print raw data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'agent-platform-local'
SERVICE = 'openhands'
FORMAT = '''{"running":{{json .State.Running}},"user":{{json .Config.User}},"image":{{json .Image}},"apparmor":{{json .AppArmorProfile}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}},"ports":{{json .NetworkSettings.Ports}},"privileged":{{json .HostConfig.Privileged}},"caps_add":{{json .HostConfig.CapAdd}},"caps_drop":{{json .HostConfig.CapDrop}},"security_opt":{{json .HostConfig.SecurityOpt}},"devices":{{json .HostConfig.Devices}},"device_requests":{{json .HostConfig.DeviceRequests}},"pid_mode":{{json .HostConfig.PidMode}},"ipc_mode":{{json .HostConfig.IpcMode}},"network_mode":{{json .HostConfig.NetworkMode}},"memory":{{json .HostConfig.Memory}},"cpus":{{json .HostConfig.NanoCpus}},"pids":{{json .HostConfig.PidsLimit}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"logging":{{json .HostConfig.LogConfig}}}'''
PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path
s = {line.split(':', 1)[0]:line.split(':', 1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if ':' in line}
p = {line.split(':', 1)[0]:line.split(':', 1)[1].strip() for line in Path('/proc/1/status').read_text().splitlines() if ':' in line}
try: apparmor = Path('/proc/self/attr/current').read_text().strip()
except OSError: apparmor = 'unavailable'
values = {}
for name in ('memory.max','cpu.max','pids.max'):
    try: values[name] = Path('/sys/fs/cgroup', name).read_text().strip()
    except OSError: values[name] = None
try:
    with open(sys.argv[1], 'rb') as canary: canary.read(1)
    host_canary_denied = False
except (FileNotFoundError, PermissionError, NotADirectoryError): host_canary_denied = True
def writable_canary(directory):
    try:
        with tempfile.TemporaryDirectory(prefix='.isolation-check-', dir=directory) as scratch:
            Path(scratch, 'synthetic.txt').write_text('synthetic canary')
        return True
    except OSError: return False
print(json.dumps({'host_canary_denied':host_canary_denied,'workspace_writable':writable_canary('/projects/demo'),'state_writable':writable_canary('/home/openhands/.openhands'),'config_writable':writable_canary('/home/openhands/.config'),'uid':os.getuid(),'pid1_uid':int(p['Uid'].split()[0]),'cap_eff':int(s['CapEff'],16),'cap_bnd':int(s['CapBnd'],16),'no_new_privs':int(s['NoNewPrivs']),'seccomp':int(s['Seccomp']),'apparmor_enforcing':apparmor.endswith('(enforce)'), 'cgroup':values}))
'''


def run(docker, args, *, input=None):
    p = subprocess.run([*docker, *args], input=input, text=True, capture_output=True, timeout=30, check=False)
    if p.returncode != 0 or len(p.stdout) > 1_000_000:
        raise RuntimeError('Docker probe failed; raw output withheld')
    return p.stdout


def row(ok):
    return {'status': 'passed' if ok else 'failed', 'reason': 'runtime_condition_satisfied' if ok else 'runtime_condition_violated'}


def numeric_limit(value, limit):
    try:
        return 0 < int(value) <= limit
    except (ValueError, TypeError):
        return False


def assess(info, proc, network, image_digests, workspace, *, expected_image):
    """Reports only fixed check identifiers, never Docker inspect or process input."""
    caps = info.get('caps_drop') or []
    opts = info.get('security_opt') or []
    mounted = info.get('mounts') or []
    persistent = [m for m in mounted if m.get('Type') != 'tmpfs']
    temporary = [m for m in mounted if m.get('Type') == 'tmpfs']
    launcher_target = '/usr/local/bin/openhands-agent-server'
    expected = {'/projects', '/home/openhands/.openhands'}
    launcher_present = any(m.get('Destination') == launcher_target for m in persistent)
    if launcher_present:
        expected.add(launcher_target)
    temporary_paths = {'/tmp', '/home/openhands/workspace', '/home/openhands/.cache', '/home/openhands/.config'}
    sources_ok = (len(persistent) == len(expected) and {m['Destination'] for m in persistent} == expected
                  and len({m['Destination'] for m in mounted}) == len(mounted)
                  and all(m.get('Destination') in temporary_paths and not m.get('Source') for m in temporary))
    for mount in persistent:
        if mount['Destination'] == '/projects':
            sources_ok &= mount['Type'] == 'bind' and Path(mount['Source']).resolve() == workspace.resolve()
        elif mount['Destination'] == '/home/openhands/.openhands':
            sources_ok &= mount['Type'] == 'volume' and mount.get('Name') == PROJECT + '_openhands-state'
        elif mount['Destination'] == launcher_target:
            sources_ok &= (mount['Type'] == 'bind' and mount.get('RW') is False
                           and Path(mount['Source']).resolve() ==
                           (ROOT/'scripts/openhands/start-agent-server.py').resolve())
        else:
            sources_ok = False
    logging = info.get('logging', {})
    limits = logging.get('Config', {})
    group = proc.get('cgroup', {})
    cpu = str(group.get('cpu.max')).split()
    try: cpu_ok = len(cpu) == 2 and 0 < int(cpu[0])/int(cpu[1]) <= 4
    except (ValueError, ZeroDivisionError): cpu_ok = False
    checks = {
        'runtime.running_pinned_image': row(info.get('running') is True and expected_image in image_digests),
        'runtime.nonroot': row(type(proc.get('uid')) is int and proc['uid'] > 0 and proc.get('pid1_uid', 0) > 0),
        'runtime.capabilities': row('ALL' in caps and not info.get('caps_add') and proc.get('cap_eff') == 0 and proc.get('cap_bnd') == 0),
        'runtime.no_new_privileges': row(any(o in {'no-new-privileges:true','no-new-privileges'} for o in opts) and proc.get('no_new_privs') == 1),
        'runtime.seccomp': row(proc.get('seccomp') == 2 and not any('seccomp=unconfined' in o for o in opts)),
        'runtime.apparmor': row(bool(info.get('apparmor')) and proc.get('apparmor_enforcing') is True),
        'runtime.namespaces_devices': row(info.get('privileged') is False and not info.get('devices') and not info.get('device_requests') and info.get('pid_mode') != 'host' and info.get('ipc_mode') != 'host' and info.get('network_mode') != 'host'),
        'runtime.mount_allowlist': row(sources_ok),
        'runtime.internal_network': row(set(info.get('networks', {})) == {PROJECT+'_agent-link'} and network.get('Internal') is True and not any(info.get('ports', {}).values())),
        'runtime.memory_cpu_pids': row(numeric_limit(info.get('memory'),6*1024**3) and numeric_limit(info.get('cpus'),4*10**9) and numeric_limit(info.get('pids'),512) and numeric_limit(group.get('memory.max'),6*1024**3) and numeric_limit(group.get('pids.max'),512) and cpu_ok),
        'runtime.log_rotation': row(logging.get('Type') == 'json-file' and limits.get('max-size') in {'5m','10m'} and limits.get('max-file') in {'2','3'}),
        'runtime.readonly_root': row(info.get('readonly') is True),
        'runtime.host_file_canary_denied': row(proc.get('host_canary_denied') is True),
        'runtime.allowed_writes': row(proc.get('workspace_writable') is True and proc.get('state_writable') is True and proc.get('config_writable') is True),
    }
    pending = ['live.cross_user_agent_canary_denied','live.agent_egress_denied','live.disk_limits','live.fair_inference_load','live.authenticated_application_isolation']
    return {'checks': checks, 'baseline': 'failed' if any(v['status']=='failed' for v in checks.values()) else 'passed',
            'pending_acceptance': pending, 'household_readiness': 'pending',
            'rootless_userns': 'not_verified',
            'scope': 'Selected current single-agent Docker/process controls; no tenant, egress, disk-quota or escape-resistance certification'}


def save(report):
    directory = ROOT / 'artifacts/security'
    if directory.is_symlink() or directory.parent.is_symlink(): raise RuntimeError('Linked report directory')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', prefix='container-', suffix='.json', dir=directory, delete=False) as stream:
        os.chmod(stream.name, 0o600);json.dump(report, stream, indent=2);stream.write('\n')
        return stream.name


class ProbeFailure(Exception):
    """Fixed error category; do not include subprocess/parser exception text."""
    def __init__(self, code, state=None):
        self.code = code
        self.state = state


def load_expected_image(path=ROOT/'infra/openhands/versions.yaml'):
    """Use the deployment lock; reject missing, mutable or malformed references."""
    try:
        lock = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ProbeFailure('image_lock_invalid') from None
    image = lock.get('image') if isinstance(lock, dict) else None
    if (not isinstance(image, str) or not re.fullmatch(
            r'ghcr\.io/openhands/agent-canvas@sha256:[0-9a-f]{64}', image)):
        raise ProbeFailure('image_lock_invalid')
    return image


STATE_FORMAT = '{"running":{{json .State.Running}},"status":{{json .State.Status}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}}}'


def collect(docker):
    expected_image = load_expected_image()
    try:
        run(docker, ['info', '--format', '{{.ServerVersion}}'])
    except Exception:
        raise ProbeFailure('docker_access_unavailable') from None
    ids = run(docker, ['ps','-a','-q','--filter','label=com.docker.compose.project='+PROJECT,'--filter','label=com.docker.compose.service='+SERVICE]).split()
    if not ids:
        raise ProbeFailure('agent_not_found')
    if len(ids) != 1:
        raise ProbeFailure('agent_selection_ambiguous')
    state = json.loads(run(docker, ['inspect','--format',STATE_FORMAT,ids[0]]))
    known_states = {'created','running','paused','restarting','removing','exited','dead'}
    if (not isinstance(state, dict) or set(state) != {'running','status','exit_code','oom_killed'}
            or type(state['running']) is not bool or state['status'] not in known_states
            or type(state['exit_code']) is not int or type(state['oom_killed']) is not bool):
        raise ProbeFailure('agent_state_unavailable')
    if not state['running'] or state['status'] != 'running':
        raise ProbeFailure('agent_not_running', state)
    info = json.loads(run(docker, ['inspect','--format',FORMAT,ids[0]]))
    with tempfile.TemporaryDirectory(prefix='agent-platform-host-canary-') as scratch:
        canary = Path(scratch) / 'synthetic.txt'
        canary.write_text('synthetic host canary')
        proc = json.loads(run(docker, ['exec','-i',ids[0],'python','-',str(canary)], input=PROBE))
    network = json.loads(run(docker, ['network','inspect','--format','{"Internal":{{json .Internal}}}',PROJECT+'_agent-link']))
    digests = json.loads(run(docker, ['image','inspect','--format','{{json .RepoDigests}}',info['image']]))
    return assess(info, proc, network, digests or [], ROOT/'artifacts/openhands/projects',
                  expected_image=expected_image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sudo', action='store_true')
    args = parser.parse_args()
    docker = ['sudo','-n','docker','--context','default'] if args.sudo else ['docker','--context','default']
    os.umask(0o077)
    try:
        report = collect(docker)
    except ProbeFailure as failure:
        report = {'baseline':'failed','household_readiness':'pending','error':failure.code}
        if failure.state is not None:
            report['agent_state'] = failure.state
    except Exception:
        report = {'baseline':'failed','household_readiness':'pending','error':'probe_failed_or_unavailable; raw details withheld'}
    report.update(time_utc=datetime.now(timezone.utc).isoformat(), checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try: path = save(report)
    except Exception:
        print('Container report could not be saved; details withheld.');return 1
    print(json.dumps(report, indent=2));print('Report: '+path)
    return 1 if report['baseline']=='failed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
