#!/usr/bin/env python3
"""Encrypted localhost identity snapshots; isolated SQL restore, never in-place."""
import argparse
import contextlib
import ctypes
import fcntl
import hashlib
import hmac
import importlib.util
import io
import json
import os
import pty
import select
import termios
from pathlib import Path, PurePosixPath
import re
import resource
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
BACKUPS = Path('/var/lib/agent-platform/identity-backups')
LIMIT = 256 * 1024**2
TABLES_SQL = "SELECT md5(string_agg(tablename, ',' ORDER BY tablename)), count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';"
class BackupError(ValueError):
    pass


def local_module():
    spec = importlib.util.spec_from_file_location('identity_backup_local', ROOT/'scripts/identity/local.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))


def terminal_phrase(timeout=600, confirm=False, prompt=None):
    """Never accept a phrase through stdin, logs, arguments or an echoing terminal."""
    with open('/dev/tty','r+b',buffering=0) as tty:
        if os.tcgetpgrp(tty.fileno())!=os.getpgrp():
            raise BackupError('recovery_terminal_not_foreground')
        original=termios.tcgetattr(tty)
        hidden=termios.tcgetattr(tty);hidden[3]&=~(termios.ECHO|termios.ECHONL)
        try:
            termios.tcsetattr(tty,termios.TCSAFLUSH,hidden)
            if termios.tcgetattr(tty)[3] & (termios.ECHO|termios.ECHONL):
                raise BackupError('recovery_terminal_echo_not_disabled')
            label=prompt.encode() if prompt is not None else (b'Confirm recovery passphrase (hidden): ' if confirm else b'Recovery passphrase (hidden): ')
            tty.write(label)
            if not select.select([tty],[],[],timeout)[0]:
                raise BackupError('recovery_phrase_input_timeout')
            value=tty.readline(4097)
            if not value.endswith(b'\n') or len(value)>4096 or not value.rstrip(b'\r\n'):
                raise BackupError('nonempty_recovery_passphrase_required')
            return value.rstrip(b'\r\n')
        finally:
            termios.tcsetattr(tty,termios.TCSADRAIN,original)
            tty.write(b'\n')


def interactive_command(args,source,target,timeout):
    # Give age its own controlling terminal. sudo's PTY/job-control state is
    # never used by the Go password reader; only our foreground reader sees it.
    pid,terminal=pty.fork()
    if pid==0:
        try:
            child_limits()
            os.dup2(source.fileno(),0);os.dup2(target.fileno(),1)
            os.execve(args[0],args,{'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root'})
        except BaseException:os._exit(126)
    deadline=time.monotonic()+timeout;buffer=b'';prompts=0;status=None
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([terminal],[],[],0.1)
            if ready:
                try:data=os.read(terminal,4096)
                except OSError:data=b''
                buffer+=data
                if len(buffer)>8192:raise BackupError('unexpected_recovery_terminal_output')
                if b'passphrase' in buffer.lower() and buffer.rstrip().endswith(b':'):
                    prompts+=1
                    if prompts>4:raise BackupError('too_many_recovery_prompts')
                    # A printed prompt can precede tcsetattr: wait for no echo
                    # before forwarding any bytes, even in automated tests.
                    for _ in range(100):
                        if not termios.tcgetattr(terminal)[3] & (termios.ECHO|termios.ECHONL):break
                        time.sleep(0.01)
                    else:raise BackupError('age_terminal_echo_not_disabled')
                    phrase=terminal_phrase(timeout=max(0,deadline-time.monotonic()),confirm=b'confirm passphrase' in buffer.lower())
                    os.write(terminal,phrase+b'\n');del phrase;buffer=b''
            done,value=os.waitpid(pid,os.WNOHANG|os.WUNTRACED)
            if done:
                if os.WIFSTOPPED(value):raise BackupError('recovery_crypto_process_stopped')
                status=value
                if not os.WIFEXITED(value) or os.WEXITSTATUS(value):
                    raise BackupError('recovery_crypto_failed_details_withheld')
                return
        raise BackupError('backup_command_timeout')
    finally:
        if status is None:
            try:os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(pid,0)
        os.close(terminal)


def stream_command(args, source, target, timeout=180, interactive=False, detached=True):
    """Keep payloads off disk/logs; kill/reap the child on timeout or interruption."""
    if interactive:
        return interactive_command(args,source,target,timeout)
    with contextlib.ExitStack() as stack:
        errors=stack.enter_context(memory_file())
        process = subprocess.Popen(args, stdin=source, stdout=target, stderr=errors,
                                   env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'HOME':'/root', 'DOCKER_CONFIG':'/nonexistent'},
                                   start_new_session=detached, preexec_fn=child_limits)
        try:
            deadline = time.monotonic()+timeout
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise BackupError('backup_command_timeout')
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    print('[identity-backup] Operation still running.', file=sys.stderr, flush=True)
            if process.returncode:
                raise BackupError('backup_command_failed_details_withheld')
        finally:
            if process.poll() is None:
                if not detached:
                    # sudo forwards SIGINT so the privileged Python helper can
                    # execute its isolated-container cleanup before termination.
                    process.send_signal(signal.SIGINT)
                    try:process.wait(timeout=75)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


@contextlib.contextmanager
def memory_file():
    # The pinned standalone CPython build omits os.memfd_create; call libc's
    # Linux API explicitly. Never fall back to a plaintext disk temporary file.
    libc = ctypes.CDLL(None, use_errno=True)
    create = libc.memfd_create
    create.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    create.restype = ctypes.c_int
    fd = create(b'identity-private', 1)  # MFD_CLOEXEC
    if fd < 0:
        raise BackupError('anonymous_memory_file_unavailable')
    with os.fdopen(fd, 'w+b') as handle:
        yield handle


def safe_read(path, maximum=LIMIT, private=False):
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        meta = os.fstat(handle.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > maximum
                or (private and (meta.st_mode & 0o077 or meta.st_uid not in {0, int(os.environ.get('SUDO_UID', str(os.getuid())))}))):
            raise BackupError('unsafe_backup_input')
        data = handle.read(maximum+1)
        if len(data) > maximum:
            raise BackupError('backup_input_too_large')
        return data


def recipient(value):
    # Native X25519 only; reject plugins, SSH recipients and injected arguments.
    if not re.fullmatch(r'age1[023456789acdefghjklmnpqrstuvwxyz]{58}', value or ''):
        raise BackupError('native_age_public_recipient_required')
    return value


def payloads(base, dump, rendered, lock):
    values = {'database.dump': dump, 'compose.yaml': rendered.encode(),
              'versions.yaml': (ROOT/'infra/identity/versions.yaml').read_bytes()}
    for name in ('manifest.json', 'secrets/postgres-password', 'secrets/authentik-password', 'secrets/authentik-secret'):
        values[name] = safe_read(base/name, 32768)
    for directory in ('data', 'certs'):
        for parent, dirs, files in os.walk(base/directory, followlinks=False):
            for child in dirs:
                if not stat.S_ISDIR((Path(parent)/child).lstat().st_mode):
                    raise BackupError('linked_identity_directory')
            for child in files:
                path = Path(parent)/child
                name = path.relative_to(base).as_posix()
                values[name] = safe_read(path)
                if sum(map(len, values.values())) > LIMIT//2 or len(values)>4096:
                    raise BackupError('backup_payload_budget_exceeded')
    if sum(map(len, values.values())) > LIMIT//2:
        raise BackupError('backup_payload_budget_exceeded')
    return values


def pack(values, lock, tables):
    metadata = {'schema':1, 'images':{key:lock[key]['image'] for key in ('postgres','authentik')},
                'public_tables': tables, 'sha256':{key:hashlib.sha256(value).hexdigest() for key,value in values.items()}}
    destination = io.BytesIO()
    with tarfile.open(fileobj=destination, mode='w') as archive:
        for name, data in {**values, 'backup.json':json.dumps(metadata, sort_keys=True).encode()}.items():
            member = tarfile.TarInfo(name)
            member.size=len(data); member.mode=0o600
            archive.addfile(member, io.BytesIO(data))
    if destination.tell()>LIMIT:
        raise BackupError('backup_payload_budget_exceeded')
    destination.seek(0)
    return destination


def unpack(handle, lock):
    """Never extract a received archive or trust its paths, types or metadata."""
    values={}; total=0
    with tarfile.open(fileobj=handle, mode='r:') as archive:
        for entry in archive:
            name=entry.name; path=PurePosixPath(name)
            if (not entry.isfile() or path.is_absolute() or '..' in path.parts or str(path)!=name
                    or name in values or entry.size<0 or entry.size>LIMIT//2 or len(values)>=4096):
                raise BackupError('unsafe_backup_archive')
            allowed={'backup.json','database.dump','compose.yaml','versions.yaml','manifest.json',
                     'secrets/postgres-password','secrets/authentik-password','secrets/authentik-secret'}
            if name not in allowed and not name.startswith(('data/','certs/')):
                raise BackupError('unexpected_backup_entry')
            total+=entry.size
            if total>LIMIT//2+32768:
                raise BackupError('backup_payload_budget_exceeded')
            values[name]=archive.extractfile(entry).read()
    required={'database.dump','compose.yaml','versions.yaml','manifest.json',
              'secrets/postgres-password','secrets/authentik-password','secrets/authentik-secret'}
    if not required<=set(values) or 'backup.json' not in values:
        raise BackupError('incomplete_backup')
    meta=json.loads(values.pop('backup.json'))
    expected={key:lock[key]['image'] for key in ('postgres','authentik')}
    if (set(meta)!={'schema','images','public_tables','sha256'} or type(meta['schema']) is not int or meta['schema']!=1
            or meta['images']!=expected or meta['sha256']!={key:hashlib.sha256(value).hexdigest() for key,value in values.items()}):
        raise BackupError('backup_integrity_or_version_mismatch')
    parse_tables(meta['public_tables'])
    if (values['secrets/postgres-password'] != values['secrets/authentik-password']
            or not re.fullmatch(rb'[a-f0-9]{64}', values['secrets/postgres-password'])
            or not re.fullmatch(rb'[a-f0-9]{96}', values['secrets/authentik-secret'])
            or not values['database.dump'].startswith(b'PGDMP')):
        raise BackupError('invalid_backup_credentials_or_dump')
    return values, meta


def parse_tables(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}\|[1-9][0-9]{0,5}',value):
        raise BackupError('invalid_database_inventory')
    return value


def table_inventory(engine, command):
    _, data = engine.run([*command,'psql','-X','-A','-t','-U','identity_local','-d','identity_local','-c',TABLES_SQL])
    return parse_tables(data.decode().strip())


def backup(engine, local, lock, rendered, config, age, public):
    recipient(public)
    local.check_state(lock, rendered)
    local.runtime(engine, config, require_all=True)
    if not BACKUPS.exists():
        BACKUPS.mkdir(mode=0o700)
    local.directory(BACKUPS,0)
    compose=['compose','--project-name',local.PROJECT,'--file',str(local.BASE/'compose.yaml')]
    pending=BACKUPS/('identity-'+uuid.uuid4().hex+'.age.partial')
    destination=pending.with_suffix('')
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    completed=False
    try:
        # Restart even after a partially successful stop; preserve the original failure.
        try:
            print('[identity-backup] Pausing Authentik server/worker for a consistent snapshot.',file=sys.stderr,flush=True)
            engine.run([*compose,'stop','--timeout','30','server','worker'],timeout=90)
            with memory_file() as dump:
                stream_command(['docker','--context','default',*compose,'exec','-T','database','pg_dump','-U','identity_local','-d','identity_local','--format=custom','--no-owner'],subprocess.DEVNULL,dump)
                dump.seek(0)
                tables=table_inventory(engine,[*compose,'exec','-T','database'])
                values=payloads(local.BASE,dump.read(),rendered,lock)
                bundle=pack(values,lock,tables)
        finally:
            print('[identity-backup] Resuming Authentik server/worker.',file=sys.stderr,flush=True)
            engine.run([*compose,'start','--wait','--wait-timeout','300','server','worker'],timeout=330)
            local.runtime(engine,config,require_all=True)
        with memory_file() as plaintext, os.fdopen(fd,'wb',closefd=False) as encrypted:
            plaintext.write(bundle.getbuffer()); plaintext.seek(0)
            stream_command([str(age),'--encrypt','--recipient',public],plaintext,encrypted)
            encrypted.flush(); os.fsync(encrypted.fileno())
        os.rename(pending,destination);completed=True
        return {'status':'created','backup_file':str(destination),'services_resumed':True,
                'restore_acceptance':'pending'}
    finally:
        os.close(fd)
        if not completed:
            pending.unlink(missing_ok=True)


def rehearsal_module():
    spec=importlib.util.spec_from_file_location('identity_rehearsal',ROOT/'scripts/identity/rehearsal.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def root_command(mode, *args):
    return ['sudo','-n','env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin',
            'SUDO_UID='+str(os.getuid()),sys.executable,'-B',str(Path(__file__).resolve()),mode,*args]


def export_ciphertext(local,path):
    # Internal privileged helper: ciphertext only, from the fixed backup root.
    if path is None or path.parent!=BACKUPS or not re.fullmatch(r'identity-[a-f0-9]{32}\.age',path.name):
        raise BackupError('fixed_private_backup_path_required')
    local.ancestors();local.directory(BACKUPS,0)
    return safe_read(path,LIMIT,private=True)


def restore_owner(lock,age,backup_path,identity,*,application=False):
    if os.geteuid()==0:raise BackupError('recovery_prompt_must_run_as_desktop_user')
    if backup_path is None or identity is None:raise BackupError('encrypted_backup_and_identity_required')
    key=safe_read(identity,65536,private=True)
    if not key.startswith(b'age-encryption.org/v1\n'):
        raise BackupError('passphrase_encrypted_recovery_identity_required')
    with memory_file() as ciphertext,memory_file() as keyfile,memory_file() as plaintext,memory_file() as result:
        print('[identity-backup] Reading protected ciphertext; no credentials requested by sudo helpers.',file=sys.stderr,flush=True)
        # Retain this session so sudo can use the terminal authentication cache.
        stream_command(root_command('read-backup','--backup',str(backup_path)),subprocess.DEVNULL,ciphertext,detached=False)
        ciphertext.seek(0);keyfile.write(key);keyfile.seek(0)
        key_path='/proc/'+str(os.getpid())+'/fd/'+str(keyfile.fileno())
        print('[identity-backup] Unlocking recovery identity as the desktop user.',file=sys.stderr,flush=True)
        stream_command([str(age),'--decrypt','--identity',key_path],ciphertext,plaintext,timeout=600,interactive=True)
        plaintext.seek(0);unpack(plaintext,lock);plaintext.seek(0)
        print('[identity-backup] Starting isolated application restore.' if application else '[identity-backup] Starting isolated SQL restore; no further passphrase prompt.',file=sys.stderr,flush=True)
        stream_command(root_command('rehearsal-load' if application else 'restore-sql'),plaintext,result,timeout=1000 if application else 600,detached=False)
        result.seek(0);report=json.loads(result.read(8192))
    if application:return rehearsal_module().validate_report(report)
    expected={'status':'passed','archive_integrity':'passed','isolated_sql_restore':'passed','cleanup':'completed',
              'scope':RESTORE_SCOPE,'household_readiness':'pending'}
    if report!=expected:raise BackupError('unexpected_privileged_restore_result')
    return report


RESTORE_SCOPE='Pinned SQL restore and public table-name inventory; not native application decryption, row-by-row equality, browser login, MFA or full host disaster recovery'


def restore_sql(engine,lock,plaintext):
    # Revalidate the entire bounded archive at the privilege boundary. No prompts.
    values,meta=unpack(plaintext,lock)
    name='agent-platform-identity-restore-'+uuid.uuid4().hex
    launched=False
    try:
        # No ports, no network, no host mounts and no persistent database volume.
        launched=True
        engine.run(['run','--detach','--pull','never','--name',name,'--label','agent-platform.identity.restore=true',
                    '--network','none','--read-only','--user','70:70','--cap-drop','ALL',
                    '--security-opt','no-new-privileges:true','--security-opt','apparmor:docker-default',
                    '--memory','768m','--cpus','1','--pids-limit','128','--log-driver','none',
                    '--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,noexec,size=512m,uid=70,gid=70,mode=0700',
                    '--tmpfs','/var/run/postgresql:rw,nosuid,nodev,noexec,size=8m,uid=70,gid=70,mode=0700',
                    '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777',
                    '--env','POSTGRES_HOST_AUTH_METHOD=trust','--env','POSTGRES_USER=identity_local',
                    '--env','POSTGRES_DB=identity_local',lock['postgres']['image']])
        for attempt in range(45):
            code,_=engine.run(['exec',name,'pg_isready','-U','identity_local','-d','identity_local'],check=False,timeout=5)
            if not code:
                break
            time.sleep(1)
        else:
            raise BackupError('isolated_postgres_not_ready')
        with memory_file() as dump, memory_file() as sink:
            dump.write(values['database.dump']);dump.seek(0)
            stream_command(['docker','--context','default','exec','-i',name,'pg_restore','-U','identity_local','-d','identity_local',
                            '--no-owner','--exit-on-error','--single-transaction'],dump,sink,timeout=300)
        if table_inventory(engine,['exec',name])!=meta['public_tables']:
            raise BackupError('restored_database_inventory_mismatch')
    finally:
        if launched:
            engine.run(['rm','--force','--volumes',name],timeout=60)
    return {'status':'passed','archive_integrity':'passed','isolated_sql_restore':'passed','cleanup':'completed',
            'scope':RESTORE_SCOPE}


def recovery_directory():
    folder=Path.home()/'.config/agent-platform/recovery'
    # Reject a redirected or writable-by-others parent before creating key material.
    for parent in reversed([folder,*folder.parents]):
        if not parent.exists():
            parent.mkdir(mode=0o700)
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0,os.getuid()} or info.st_mode&0o022:
            raise BackupError('unsafe_recovery_directory')
    if folder.stat().st_mode&0o077:
        raise BackupError('recovery_directory_requires_mode_0700')
    return folder


def key_create(age):
    if os.geteuid()==0:
        raise BackupError('generate_recovery_identity_as_desktop_user_without_sudo')
    folder=recovery_directory()
    target=folder/'identity.age';public_file=folder/'recipient.txt'
    if target.exists() or public_file.exists():
        raise BackupError('recovery_identity_exists_no_overwrite')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    complete=False
    try:
        with memory_file() as private, memory_file() as public, os.fdopen(fd,'wb',closefd=False) as output:
            stream_command([str(age.parent/'age-keygen')],subprocess.DEVNULL,private)
            private.seek(0)
            stream_command([str(age.parent/'age-keygen'),'-y'],private,public)
            public.seek(0);address=recipient(public.read(256).decode().strip())
            private.seek(0)
            print('[identity-backup] Choose a recovery passphrase in this terminal; retain it privately.',file=sys.stderr,flush=True)
            stream_command([str(age),'--passphrase'],private,output,timeout=600,interactive=True)
            output.flush();os.fsync(output.fileno())
        # Preserve a successfully encrypted key even if saving its public key fails.
        complete=True
        pubfd=os.open(public_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(pubfd,'w') as output:
            output.write(address+'\n');output.flush();os.fsync(output.fileno())
        return {'status':'prepared','encrypted_identity':str(target),'public_recipient_file':str(public_file),
                'offline_copy':'pending','scope':'Encrypted key generated only; no backup or service changes'}
    finally:
        os.close(fd)
        if not complete:
            target.unlink(missing_ok=True)


def key_rewrap(age):
    if os.geteuid()==0:raise BackupError('rewrap_recovery_identity_as_desktop_user_without_sudo')
    folder=recovery_directory();identity=folder/'identity.age'
    original=safe_read(identity,65536,private=True)
    public=recipient(safe_read(folder/'recipient.txt',256,private=True).decode().strip())
    if not original.startswith(b'age-encryption.org/v1\n'):
        raise BackupError('passphrase_encrypted_recovery_identity_required')
    pending=folder/('identity-rewrap-'+uuid.uuid4().hex+'.partial')
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with memory_file() as encrypted,memory_file() as plain,memory_file() as observed:
            encrypted.write(original);encrypted.seek(0)
            print('[identity-backup] Unlock the existing recovery identity.',file=sys.stderr,flush=True)
            stream_command([str(age),'--decrypt'],encrypted,plain,timeout=600,interactive=True)
            plain.seek(0)
            stream_command([str(age.parent/'age-keygen'),'-y'],plain,observed)
            observed.seek(0)
            if observed.read().decode().strip()!=public:raise BackupError('recovery_public_key_mismatch')
            plain.seek(0)
            with os.fdopen(fd,'wb',closefd=False) as output:
                print('[identity-backup] Choose and confirm a NEW recovery passphrase.',file=sys.stderr,flush=True)
                stream_command([str(age),'--passphrase'],plain,output,timeout=600,interactive=True)
                output.flush();os.fsync(output.fileno())
            with memory_file() as candidate,memory_file() as verified:
                candidate.write(safe_read(pending,65536,private=True));candidate.seek(0)
                print('[identity-backup] Verify the NEW passphrase before replacing the file.',file=sys.stderr,flush=True)
                stream_command([str(age),'--decrypt'],candidate,verified,timeout=600,interactive=True)
                plain.seek(0);verified.seek(0)
                if not hmac.compare_digest(plain.read(),verified.read()):
                    raise BackupError('rewrapped_identity_verification_failed')
            if safe_read(identity,65536,private=True)!=original:raise BackupError('recovery_identity_changed_during_rewrap')
            os.replace(pending,identity)
            directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        return {'status':'rewrapped','encrypted_identity':str(identity),'public_recipient_preserved':True,
                'existing_backups_compatible':True,'offline_copy_refresh':'required',
                'scope':'Same recovery key; old encrypted copies remain usable with the old passphrase'}
    finally:
        os.close(fd);pending.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['plan','key-create','key-rewrap','create','restore-check','read-backup','restore-sql','rehearsal-plan','rehearsal-up','rehearsal-load','rehearsal-check','rehearsal-accept','rehearsal-down'])
    parser.add_argument('--age',type=Path)
    parser.add_argument('--recipient')
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--identity',type=Path)
    args=parser.parse_args()
    try:
        local=local_module();helper,lock,rendered,config=local.bundle()
        if args.mode=='rehearsal-plan':
            report=rehearsal_module().plan(local)
        elif args.mode=='plan':
            report={'status':'prepared','encryption':'age 1.3.2 native public recipient','backup_root':str(BACKUPS),
                    'plaintext':'Anonymous memory-backed files; host swap/core policy still matters',
                    'service_interruption':'create pauses and resumes server/worker; database remains running',
                    'restore_check':'Disposable pinned PostgreSQL; no network, published ports or host mounts'}
        else:
            if args.mode=='read-backup':
                if os.geteuid()!=0:raise BackupError('host_admin_required')
                data=export_ciphertext(local,args.backup)
                sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
                return 0
            if args.mode not in ('restore-sql','rehearsal-load','rehearsal-check','rehearsal-accept','rehearsal-down') and (not args.age or not args.age.is_absolute()):
                raise BackupError('absolute_mise_age_path_required')
            if args.mode not in ('restore-sql','rehearsal-load','rehearsal-check','rehearsal-accept','rehearsal-down'):
                with memory_file() as output:
                    stream_command([str(args.age),'--version'],subprocess.DEVNULL,output)
                    output.seek(0)
                    if output.read().strip()!=b'v1.3.2':
                        raise BackupError('pinned_age_required')
            if args.mode in ('key-create','key-rewrap'):
                report=key_create(args.age) if args.mode=='key-create' else key_rewrap(args.age)
                print(json.dumps(report,indent=2))
                return 0
            if args.mode in ('restore-check','rehearsal-up'):
                report=restore_owner(lock,args.age,args.backup,args.identity,application=args.mode=='rehearsal-up')
                print(json.dumps(report,indent=2))
                return 0
            if os.geteuid()!=0:
                raise BackupError('host_admin_required')
            local.ancestors()
            lockfd=os.open(local.BASE.parent/'identity-local.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            with os.fdopen(lockfd,'wb') as guard:
                fd=guard.fileno();info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_mode&0o077:
                    raise BackupError('unsafe_identity_lock')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                engine=helper.Engine()
                if args.mode=='create':
                    report=backup(engine,local,lock,rendered,config,args.age,args.recipient)
                elif args.mode in ('rehearsal-check','rehearsal-accept'):
                    report=rehearsal_module().check(engine,local,accept=args.mode=='rehearsal-accept')
                elif args.mode=='rehearsal-down':
                    report=rehearsal_module().stop(engine,local)
                else:
                    raw=sys.stdin.buffer.read(LIMIT+1)
                    if len(raw)>LIMIT:raise BackupError('backup_payload_budget_exceeded')
                    report=(rehearsal_module().start(engine,sys.modules[__name__],local,lock,io.BytesIO(raw))
                            if args.mode=='rehearsal-load' else restore_sql(engine,lock,io.BytesIO(raw)))
    except Exception as error:
        report={'status':'failed','error':str(error) if isinstance(error,BackupError) or type(error).__name__=='RehearsalError' else 'identity_backup_failed_details_withheld'}
    report['household_readiness']='pending'
    print(json.dumps(report,indent=2))
    return int(report['status']=='failed')


if __name__=='__main__':
    raise SystemExit(main())
