#!/usr/bin/env python3
"""Prepare a bounded synthetic storage pilot; never migrate existing agents or data."""
import argparse
from datetime import datetime, timezone
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/var/lib/agent-platform/storage-pilot')
POLICY = ROOT/'config/storage/pilot.yaml'
MIB = 1024**2
GIB = 1024**3
TOOLS = ('findmnt', 'losetup', 'mkfs.ext4', 'mount', 'umount')


class StorageError(ValueError):
    """Fixed public category; raw paths, command output and exceptions are withheld."""


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    values = {}
    for key_node, value_node in node.value:
        if isinstance(key_node, yaml.SequenceNode) or isinstance(key_node, yaml.MappingNode):
            raise StorageError('invalid_policy')
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in values:
            raise StorageError('invalid_policy')
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def read_yaml(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise StorageError('invalid_policy')
    try:
        return yaml.load(path.read_text(), Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError):
        raise StorageError('invalid_policy') from None


def load_policy(path=POLICY):
    policy = read_yaml(path)
    if (not isinstance(policy, dict) or set(policy) !=
            {'schema_version','purpose','host_reserve_gib','volumes_mib','tenants'}
            or policy['schema_version'] != 1 or type(policy['schema_version']) is not int
            or policy['purpose'] != 'synthetic_storage_probe'
            or type(policy['host_reserve_gib']) is not int
            or not 20 <= policy['host_reserve_gib'] <= 100):
        raise StorageError('invalid_policy')
    volumes = policy['volumes_mib']
    if (not isinstance(volumes, dict) or set(volumes) != {'workspace','state'}
            or any(type(v) is not int or v != 128 for v in volumes.values())):
        raise StorageError('invalid_policy')
    tenants = policy['tenants']
    if not isinstance(tenants, list) or len(tenants) != 2:
        raise StorageError('invalid_policy')
    for tenant in tenants:
        if (not isinstance(tenant, dict) or set(tenant) != {'id','uid','gid'}
                or not isinstance(tenant['id'],str) or tenant['id'] not in {'probe-a','probe-b'}
                or type(tenant['uid']) is not int or type(tenant['gid']) is not int
                or not 200000 <= tenant['uid'] <= 299999 or tenant['gid'] != tenant['uid']):
            raise StorageError('invalid_policy')
    if len({t['id'] for t in tenants}) != 2 or len({t['uid'] for t in tenants}) != 2:
        raise StorageError('invalid_policy')
    return policy


def policy_hash(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def entries(policy, base=BASE):
    return [(tenant, role, size*MIB,
             base/'images'/f"{tenant['id']}-{role}.ext4",
             base/'mounts'/tenant['id']/role)
            for tenant in policy['tenants']
            for role, size in policy['volumes_mib'].items()]


def safe_path(path, owner=0):
    """Managed ancestors must be owned by the administrator and not writable by others."""
    for item in [path, *path.parents]:
        try:
            details = item.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(details.st_mode) or details.st_uid != owner
                or details.st_mode & 0o022):
            raise StorageError('unsafe_managed_path')


def safe_image(path, size, owner=0):
    details = path.lstat()
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != owner
            or details.st_nlink != 1 or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_size != size or details.st_blocks*512 < size):
        raise StorageError('invalid_backing_file')


def reserve_image(path, size, owner=0):
    """Formatting can free extents; re-reserve only a verified new regular image."""
    fd = os.open(path,os.O_WRONLY|os.O_NOFOLLOW)
    try:
        details = os.fstat(fd)
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != owner
                or details.st_nlink != 1 or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_size != size):
            raise StorageError('invalid_backing_file')
        os.posix_fallocate(fd,0,size);os.fsync(fd)
    finally:
        os.close(fd)


def require_unused_ids(policy):
    for tenant in policy['tenants']:
        for lookup, value in ((pwd.getpwuid,tenant['uid']), (grp.getgrgid,tenant['gid'])):
            try:
                lookup(value)
            except KeyError:
                continue
            raise StorageError('host_identity_collision')


class Engine:
    def run(self, args, *, input=None, timeout=30):
        try:
            result = subprocess.run(args, input=input, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise StorageError('operation_unavailable_or_timed_out') from None
        if result.returncode:
            raise StorageError('operation_failed')
        if len(result.stdout) > 1_000_000:
            raise StorageError('invalid_operation_output')
        return result.stdout

    def mount_info(self, target):
        # --mountpoint rejects parent-filesystem fallbacks when the loop is absent.
        result = subprocess.run(['findmnt','--json','--mountpoint',str(target),
                                 '--output','TARGET,SOURCE,FSTYPE,OPTIONS'],
                                capture_output=True, timeout=10)
        if result.returncode == 1:
            return None
        if result.returncode or len(result.stdout) > 65536:
            raise StorageError('mount_probe_failed')
        data = json.loads(result.stdout)
        rows = data.get('filesystems', [])
        if len(rows) != 1:
            raise StorageError('mount_probe_failed')
        return rows[0]

    def backing_file(self, device):
        if not re.fullmatch(r'/dev/loop[0-9]+', device):
            raise StorageError('unexpected_mount_source')
        data = json.loads(self.run(['losetup','--json','--list',device,
                                   '--output','NAME,BACK-FILE']))
        rows = data.get('loopdevices', [])
        if len(rows) != 1 or rows[0].get('name') != device:
            raise StorageError('unexpected_mount_source')
        return rows[0].get('back-file')


def verify_mount(entry, engine):
    tenant, role, size, image, target = entry
    safe_path(image.parent)
    safe_path(target.parent)
    safe_image(image, size)
    info = engine.mount_info(target)
    if info is None:
        raise StorageError('required_mount_missing')
    options = set(info.get('options','').split(','))
    if (info.get('target') != str(target) or info.get('fstype') != 'ext4'
            or not {'rw','nodev','nosuid','noexec'} <= options
            or 'discard' in options or engine.backing_file(info.get('source','')) != str(image)):
        raise StorageError('mount_boundary_mismatch')
    details = target.lstat()
    fs = os.statvfs(target)
    if (stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode)
            or details.st_uid != tenant['uid'] or details.st_gid != tenant['gid']
            or stat.S_IMODE(details.st_mode) != 0o700
            or not 0 < fs.f_blocks*fs.f_frsize <= size):
        raise StorageError('mount_identity_or_capacity_mismatch')
    return {'tenant':tenant['id'], 'role':role, 'capacity_mib':size//MIB,
            'usable_mib':round(fs.f_blocks*fs.f_frsize/MIB,2), 'status':'passed'}


def inspect_record(policy, base=BASE):
    safe_path(base)
    record = base/'record.yaml'
    if record.is_symlink() or not record.is_file():
        raise StorageError('unprepared_or_partial_pilot')
    details = record.stat()
    if details.st_uid != 0 or stat.S_IMODE(details.st_mode) != 0o600 or details.st_nlink != 1:
        raise StorageError('invalid_pilot_record')
    expected = {'schema_version':1,'purpose':policy['purpose'],
                'policy_sha256':policy_hash(policy)}
    if read_yaml(record) != expected:
        raise StorageError('pilot_policy_mismatch')


def backing_filesystem(base=BASE):
    ancestor = base
    while not ancestor.exists():
        ancestor = ancestor.parent
    data = json.loads(Engine().run(['findmnt','--json','--target',str(ancestor),
                                    '--output','FSTYPE']))
    rows = data.get('filesystems', [])
    if len(rows) != 1:
        raise StorageError('backing_filesystem_unavailable')
    return rows[0].get('fstype')


def available_capacity(policy, base=BASE):
    ancestor = base
    while not ancestor.exists():
        ancestor = ancestor.parent
    required = sum(entry[2] for entry in entries(policy,base))
    free = shutil.disk_usage(ancestor).free
    return required, free, free >= required + policy['host_reserve_gib']*GIB


def plan(policy):
    filesystem = backing_filesystem()
    if filesystem != 'ext4':
        raise StorageError('unsupported_backing_filesystem')
    required, free, capacity = available_capacity(policy)
    require_unused_ids(policy)
    return {'status':'planned' if capacity else 'failed', 'purpose':policy['purpose'],
            'allocation_mib':required//MIB, 'storage_root':str(BASE), 'backing_free_gib':round(free/GIB,2),
            'host_reserve_gib':policy['host_reserve_gib'], 'backing_filesystem':filesystem,
            'tools':{tool:'available' if shutil.which(tool) else 'missing' for tool in TOOLS},
            'capacity':'passed' if capacity else 'failed',
            'host_setup':'pending', 'live_acceptance':'pending',
            'scope':'Two synthetic identities only; no allocation, migration or household acceptance'}


def prepare(policy, engine, base=BASE):
    require_unused_ids(policy)
    safe_path(base)
    if base.exists():
        inspect_record(policy,base)
        prepared = entries(policy,base)
        # Validate every file before remounting anything; never format existing images.
        for _, _, size, image, target in prepared:
            safe_path(image.parent);safe_path(target.parent);safe_image(image,size)
    else:
        if not available_capacity(policy,base)[2]:
            raise StorageError('insufficient_reserved_capacity')
        base.parent.mkdir(mode=0o700,exist_ok=True)
        base.mkdir(mode=0o700)
        (base/'images').mkdir(mode=0o700)
        (base/'mounts').mkdir(mode=0o700)
        prepared = entries(policy,base)
        for tenant, role, size, image, target in prepared:
            print(f'[storage] Preparing {tenant["id"]}/{role} ({size//MIB} MiB).',file=sys.stderr,flush=True)
            target.parent.mkdir(mode=0o700,exist_ok=True)
            target.mkdir(mode=0o700)
            # O_EXCL prevents overwriting anything, including a partial prior setup.
            fd = os.open(image,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                os.posix_fallocate(fd,0,size)
                os.fsync(fd)
            finally:
                os.close(fd)
            safe_image(image,size)
            engine.run(['mkfs.ext4','-q','-F','-m','0','-E',
                        'nodiscard,lazy_itable_init=0,lazy_journal_init=0',str(image)],timeout=120)
            reserve_image(image,size)
            safe_image(image,size)
        # Marker is saved after all files were formatted, before mounting. Setup can
        # recover unmounted completed files; incomplete allocation fails closed.
        record = base/'record.yaml'
        with record.open('x') as output:
            os.chmod(record,0o600)
            yaml.safe_dump({'schema_version':1,'purpose':policy['purpose'],
                            'policy_sha256':policy_hash(policy)},output)
            output.flush();os.fsync(output.fileno())
    for entry in prepared:
        tenant, role, size, image, target = entry
        info = engine.mount_info(target)
        if info is None:
            # No fallback directory may contain data or linked paths.
            safe_path(target)
            if any(target.iterdir()):
                raise StorageError('nonempty_unmounted_target')
            print(f'[storage] Mounting {tenant["id"]}/{role}.',file=sys.stderr,flush=True)
            engine.run(['mount','-t','ext4','-o','loop,rw,nodev,nosuid,noexec,nodiscard',
                        str(image),str(target)])
            os.chown(target,tenant['uid'],tenant['gid']);os.chmod(target,0o700)
        verify_mount(entry,engine)
    return {'status':'prepared','volumes':[verify_mount(e,engine) for e in prepared],
            'live_acceptance':'pending','household_readiness':'pending',
            'scope':'Synthetic pilot only; existing OpenHands mounts and data unchanged'}


def check(policy,engine,base=BASE):
    inspect_record(policy,base)
    require_unused_ids(policy)
    return {'status':'passed','volumes':[verify_mount(e,engine) for e in entries(policy,base)],
            'live_acceptance':'pending','household_readiness':'pending',
            'scope':'Synthetic backing/mount checks; ENOSPC and cross-user probes still required'}


def unmount(policy,engine,base=BASE):
    inspect_record(policy,base)
    selected = []
    for entry in entries(policy,base):
        if engine.mount_info(entry[4]) is not None:
            verify_mount(entry,engine);selected.append(entry)
    for entry in reversed(selected):
        # Never force or lazily detach busy mounts. Files/images are not deleted.
        engine.run(['umount',str(entry[4])])
    return {'status':'unmounted','images_preserved':True,'household_readiness':'pending'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['plan','setup','check','unmount','accept'])
    args = parser.parse_args()
    os.umask(0o077)
    try:
        policy = load_policy()
        if args.mode == 'plan':
            report = plan(policy)
        else:
            if os.geteuid() != 0:
                raise StorageError('host_admin_required')
            if any(not shutil.which(tool) for tool in TOOLS):
                raise StorageError('host_tool_missing')
            if backing_filesystem(BASE) != 'ext4':
                raise StorageError('unsupported_backing_filesystem')
            # Fixed root-owned lock outside writable mounts; no report imports.
            safe_path(BASE.parent)
            if args.mode == 'setup':
                BASE.parent.mkdir(mode=0o700,exist_ok=True)
            elif not BASE.parent.is_dir():
                raise StorageError('unprepared_or_partial_pilot')
            lock = BASE.parent/'storage-pilot.lock'
            flags = os.O_WRONLY|os.O_NOFOLLOW
            if args.mode == 'setup': flags |= os.O_CREAT
            fd = os.open(lock,flags,0o600)
            try:
                details = os.fstat(fd)
                if details.st_uid != 0 or details.st_nlink != 1 or stat.S_IMODE(details.st_mode) != 0o600:
                    raise StorageError('unsafe_managed_path')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                engine = Engine()
                if args.mode == 'setup': report = prepare(policy,engine)
                elif args.mode == 'check': report = check(policy,engine)
                elif args.mode == 'unmount': report = unmount(policy,engine)
                else:
                    from acceptance import accept
                    report = accept(policy,engine,sys.modules[__name__])
            finally:
                os.close(fd)
    except StorageError as exc:
        report = {'status':'failed','error':str(exc),'household_readiness':'pending'}
    except Exception:
        report = {'status':'failed','error':'storage_operation_failed_details_withheld',
                  'household_readiness':'pending'}
    report.update(time_utc=datetime.now(timezone.utc).isoformat(),
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(report,indent=2))
    return 1 if report['status'] == 'failed' or 'missing' in report.get('tools',{}).values() else 0


if __name__ == '__main__':
    raise SystemExit(main())
