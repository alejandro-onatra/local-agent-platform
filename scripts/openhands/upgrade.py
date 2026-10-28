#!/usr/bin/env python3
"""Preflight and back up a pinned, single-agent OpenHands upgrade on the host."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE = 'agent-platform-local_openhands-state'
PROJECT = 'agent-platform-local'
OH_ENV = 'OH_HOST_GID,OH_WORKSPACE,OH_ISOLATED_UID,OH_ISOLATED_GID,OH_ISOLATED_USER'
INSPECT = '''{"running":{{json .State.Running}},"image":{{json .Image}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}'''


class UpgradeError(RuntimeError):
    """Fixed, public diagnostic; never includes Docker output or archive names."""


class Engine:
    def __init__(self, sudo=False):
        self.docker = (['sudo'] if sudo else []) + ['docker', '--context', 'default']
        compose = ['docker', '--context', 'default', 'compose']
        if sudo:
            compose = ['sudo', '--preserve-env='+OH_ENV] + compose
        self.compose = compose + ['-f', str(ROOT/'infra/llm/compose.yaml'),
                                  '-f', str(ROOT/'infra/openhands/compose.yaml')]
        if os.environ.get('OH_ISOLATED_USER'):
            self.compose += ['-f', str(ROOT/'infra/openhands/hardening.yaml')]

    def execute(self, command, *, input=None, output=None, timeout=60):
        try:
            result = subprocess.run(command, input=input, stdout=output or subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise UpgradeError('Docker operation unavailable or timed out') from None
        if result.returncode:
            raise UpgradeError('Docker operation failed; raw output withheld')
        return result.stdout if output is None else b''

    def pull(self, image, timeout=1800):
        # Fixed heartbeat avoids a silent multi-minute download or raw CLI output.
        process = subprocess.Popen(self.docker+['pull', image], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            while process.poll() is None:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic()-started
                    print(f'[upgrade] Image download still running ({int(elapsed)}s).', flush=True)
                    if elapsed >= timeout:
                        raise UpgradeError('Image download timed out')
            if process.returncode:
                raise UpgradeError('Pinned image download failed; raw details withheld')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()

    def d(self, *args, **kwargs):
        return self.execute(self.docker+list(args), **kwargs)

    def c(self, *args):
        return self.execute(self.compose+list(args))


def private_directory(path):
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise UpgradeError('Linked backup directory rejected')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise UpgradeError('Backup directory owner mismatch')
    os.chmod(path, 0o700)
    return path


def selected_container(engine, lock, *, required=True):
    selected = engine.c('ps', '--all', '-q', 'openhands').decode().strip()
    if not selected and not required:
        return None
    if not re.fullmatch(r'[a-f0-9]{12,64}', selected):
        raise UpgradeError('Cannot select one existing OpenHands container')
    info = json.loads(engine.d('inspect', '--format', INSPECT, selected))
    labels = info['labels']
    if labels.get('com.docker.compose.project') != PROJECT or labels.get('com.docker.compose.service') != 'openhands':
        raise UpgradeError('OpenHands container identity mismatch')
    digests = json.loads(engine.d('image', 'inspect', '--format', '{{json .RepoDigests}}', info['image']))
    allowed = [lock['image'], lock['upgrade_from']['image']]
    actual = next((digest for digest in allowed if digest in (digests or [])), None)
    if actual is None:
        raise UpgradeError('Existing OpenHands image is not a recognized pinned release')
    return info, actual


def safe_backup_sources(info):
    mounts = info['mounts']
    state = [m for m in mounts if m['Destination'] == '/home/openhands/.openhands']
    projects = [m for m in mounts if m['Destination'] == '/projects']
    if len(state) != 1 or state[0].get('Type') != 'volume' or state[0].get('Name') != STATE:
        raise UpgradeError('Unexpected state volume; backup refused')
    expected = ROOT/'artifacts/openhands/projects'
    if (len(projects) != 1 or projects[0].get('Type') != 'bind'
            or Path(projects[0]['Source']).resolve() != expected.resolve()):
        raise UpgradeError('Unexpected workspace mount; backup refused')
    return expected


def isolation(uid, gid):
    return ['--network', 'none', '--read-only', '--user', f'{uid}:{gid}',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--security-opt', 'apparmor=docker-default', '--memory', '2g',
            '--cpus', '2', '--pids-limit', '128']


def preflight(engine, lock, uid, gid):
    print('[upgrade] Pulling the pinned candidate image; existing services keep running.', flush=True)
    engine.pull(lock['image'])
    base = ['run', '--rm', '-i', *isolation(uid, gid),
            '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777',
            '--env', 'HOME=/tmp', '--env', 'LITELLM_LOCAL_MODEL_COST_MAP=true',
            '--env', 'OPENHANDS_SUPPRESS_BANNER=1', '--entrypoint', 'python', lock['image']]
    identity = engine.d(*base, '-c', 'import pwd; p=pwd.getpwnam("openhands"); print(f"{p.pw_uid}:{p.pw_gid}")').decode().strip()
    if identity != f'{uid}:{gid}':
        raise UpgradeError('Candidate image UID/GID differs from verified activation')
    engine.d(*base, '-', '--runtime-check', input=(ROOT/'scripts/openhands/start-agent-server.py').read_bytes(), timeout=120)
    print('[upgrade] Candidate identity, installed modules and native cache-usage self-test passed.', flush=True)


def backup(engine, helper, uid, gid, directory, workspace):
    host_gid = os.environ['OH_HOST_GID']
    if not host_gid.isdigit():
        raise UpgradeError('Host group is invalid')
    base = ['run', '--rm', *isolation(uid, gid), '--group-add', host_gid,
            '--mount', f'type=volume,src={STATE},dst=/source-state,readonly',
            '--mount', f'type=bind,src={workspace},dst=/source-projects,readonly',
            '--entrypoint', 'tar', helper]
    hashes = {}
    for name, source in [('state', '/source-state'), ('projects', '/source-projects')]:
        path = directory/(name+'.tar')
        with path.open('xb') as output:
            os.chmod(path, 0o600)
            engine.d(*base, '-C', source, '-cf', '-', '.', output=output, timeout=1800)
        # Archive validation prints no entry names or content.
        result = subprocess.run(['tar', '-tf', str(path)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=180, check=False)
        if result.returncode:
            raise UpgradeError('Backup archive validation failed')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
    manifest = directory/'manifest.json'
    manifest.write_text(json.dumps({'archives_sha256': hashes, 'scope': 'Stopped OpenHands state and projects; private local unencrypted backup'}, indent=2)+'\n')
    os.chmod(manifest, 0o600)


def apply(engine, lock, helper, uid, gid, info, workspace, base):
    engine.pull(helper, timeout=300)
    # Check before stopping; archive failure restarts existing containers.
    if shutil.disk_usage(base).free < 2*1024**3:
        raise UpgradeError('Less than 2 GiB backup space; upgrade refused')
    directory = Path(tempfile.mkdtemp(prefix='openhands-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-', dir=base))
    changed = False
    stopped = False
    print('[upgrade] Stopping only OpenHands/proxy to create consistent local backups.', flush=True)
    try:
        engine.c('stop', 'openhands', 'openhands-proxy')
        stopped = True
        backup(engine, helper, uid, gid, directory, workspace)
        print(f'[upgrade] Validated private backup: {directory}', flush=True)
        changed = True  # up may partially recreate before returning an error.
        engine.c('up', '-d', '--no-deps', '--force-recreate', 'openhands', 'openhands-proxy')
        result = subprocess.run(['bash', str(ROOT/'scripts/openhands/check.sh')], check=False)
        if result.returncode:
            raise UpgradeError('Candidate health checks failed')
    except BaseException:
        try:
            if stopped and not changed and info['running']:
                engine.c('start', 'openhands', 'openhands-proxy')
            elif changed:
                engine.c('stop', 'openhands', 'openhands-proxy')
        except UpgradeError:
            print('[upgrade] Service recovery/stop failed; inspect status locally.', file=sys.stderr)
        print(f'[upgrade] Backup directory: {directory}. No automatic state downgrade or deletion performed.', file=sys.stderr)
        raise
    print('[upgrade] New UI/backend/model checks passed. Real agent execution and post-upgrade restrictions remain pending.')
    print('[upgrade] Refresh observability log mounts after recreation: task observability:logs:configure.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan', 'apply', 'guard-up'])
    parser.add_argument('--sudo', action='store_true')
    args = parser.parse_args()
    lock = yaml.safe_load((ROOT/'infra/openhands/versions.yaml').read_text())
    engine = Engine(args.sudo)
    if args.mode != 'guard-up' and not os.environ.get('OH_ISOLATED_USER'):
        raise UpgradeError('Active non-root hardening profile required')
    selected = selected_container(engine, lock, required=args.mode != 'guard-up')
    if args.mode == 'guard-up':
        if selected and selected[1] != lock['image']:
            raise UpgradeError('Older pinned OpenHands found; use task openhands:upgrade:apply for backups and preflight')
        return
    # The shared shell helper has already validated the protected activation file.
    uid, gid = int(os.environ['OH_ISOLATED_UID']), int(os.environ['OH_ISOLATED_GID'])
    if uid <= 0 or gid <= 0 or os.environ['OH_ISOLATED_USER'] != f'{uid}:{gid}':
        raise UpgradeError('Active non-root hardening profile required')
    info, image = selected
    workspace = safe_backup_sources(info)
    base = private_directory(Path.home()/'.local/share/agent-platform/backups')
    with (base/'openhands-upgrade.lock').open('a') as operation:
        os.chmod(base/'openhands-upgrade.lock', 0o600)
        try:
            fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpgradeError('Another upgrade is already running') from None
        preflight(engine, lock, uid, gid)
        if args.mode == 'apply':
            helper = yaml.safe_load((ROOT/'infra/host/versions.yaml').read_text())['smoke_images']['ubuntu']
            apply(engine, lock, helper, uid, gid, info, workspace, base)
        else:
            print('[upgrade] Plan passed; no services stopped, archives created or persistent data changed.')


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        message = str(error) if isinstance(error, UpgradeError) else 'Upgrade interrupted or unavailable; raw details withheld'
        print('[upgrade] '+message, file=sys.stderr)
        raise SystemExit(1)
