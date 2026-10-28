"""Backup rejection, service recovery, native crypto and restore cleanup tests."""
import hashlib
import importlib.util
import io
import json
import os
import pty
import select
import time
import signal
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('identity_backup_tested',ROOT/'scripts/identity/backup.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
LOCK={name:{'image':name+'@sha256:'+'a'*64} for name in ('postgres','authentik')}
TABLES='a'*32+'|42'

def values():
    return {'database.dump':b'PGDMPsynthetic', 'compose.yaml':b'synthetic', 'versions.yaml':b'pinned',
            'manifest.json':b'{}','secrets/postgres-password':b'a'*64,
            'secrets/authentik-password':b'a'*64,'secrets/authentik-secret':b'b'*96,
            'data/empty':b'', 'certs/sample':b'synthetic'}

def archive(entries):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as bundle:
        for name,data,kind in entries:
            entry=tarfile.TarInfo(name);entry.type=kind;entry.size=len(data)
            bundle.addfile(entry,io.BytesIO(data))
    output.seek(0);return output


class ArchiveTests(unittest.TestCase):
    def test_round_trip_preserves_all_bytes_including_empty_files(self):
        original=values();parsed,metadata=B.unpack(B.pack(original,LOCK,TABLES),LOCK)
        self.assertEqual(parsed,original);self.assertEqual(metadata['public_tables'],TABLES)

    def test_missing_signing_key_or_database_rejected(self):
        for name in ('database.dump','secrets/authentik-secret','manifest.json'):
            with self.subTest(name=name):
                content=values();content.pop(name)
                with self.assertRaisesRegex(B.BackupError,'incomplete_backup'):
                    B.unpack(B.pack(content,LOCK,TABLES),LOCK)

    def test_different_images_rejected(self):
        other={**LOCK,'postgres':{'image':'other'}}
        with self.assertRaisesRegex(B.BackupError,'version_mismatch'):
            B.unpack(B.pack(values(),LOCK,TABLES),other)

    def test_mismatched_password_copies_bad_key_and_dump_fail(self):
        for name,data in [('secrets/authentik-password',b'c'*64),('secrets/authentik-secret',b'bad'),('database.dump',b'bad')]:
            content=values();content[name]=data
            with self.subTest(name=name), self.assertRaisesRegex(B.BackupError,'credentials_or_dump'):
                B.unpack(B.pack(content,LOCK,TABLES),LOCK)

    def test_archive_path_traversal_links_duplicates_and_unknown_entries_rejected(self):
        for entries in [[('../outside',b'x',tarfile.REGTYPE)], [('/absolute',b'x',tarfile.REGTYPE)],
                        [('data/link',b'',tarfile.SYMTYPE)], [('data/pipe',b'',tarfile.FIFOTYPE)],
                        [('database.dump',b'x',tarfile.REGTYPE)]*2, [('unexpected',b'x',tarfile.REGTYPE)]]:
            with self.subTest(entries=entries), self.assertRaises(B.BackupError):
                B.unpack(archive(entries),LOCK)

    def test_modified_payload_digest_and_boolean_schema_rejected(self):
        original=values();valid=B.pack(original,LOCK,TABLES)
        with tarfile.open(fileobj=valid) as source:
            entries=[(entry.name,source.extractfile(entry).read(),tarfile.REGTYPE) for entry in source]
        altered=[(name,b'changed' if name=='data/empty' else data,kind) for name,data,kind in entries]
        with self.assertRaisesRegex(B.BackupError,'integrity'):
            B.unpack(archive(altered),LOCK)
        altered=[]
        for name,data,kind in entries:
            if name=='backup.json':
                meta=json.loads(data);meta['schema']=True;data=json.dumps(meta).encode()
            altered.append((name,data,kind))
        with self.assertRaises(B.BackupError):B.unpack(archive(altered),LOCK)

    def test_no_recipient_plugins_or_empty_inventory(self):
        for public in ('','-R /tmp/file','age-plugin-test','ssh-ed25519 AAAA'):
            with self.assertRaises(B.BackupError):B.recipient(public)
        for inventory in ('a'*32+'|0','secret',False):
            with self.assertRaises(B.BackupError):B.parse_tables(inventory)


class FileTests(unittest.TestCase):
    def test_symlink_hardlink_fifo_and_public_keyfile_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'key';file.write_bytes(b'private');file.chmod(0o600)
            self.assertEqual(B.safe_read(file,private=True),b'private')
            file.chmod(0o644)
            with self.assertRaises(B.BackupError):B.safe_read(file,private=True)
            file.chmod(0o600);link=root/'link';link.hardlink_to(file)
            with self.assertRaises(B.BackupError):B.safe_read(file)
            link.unlink();link.symlink_to(file)
            with self.assertRaises(OSError):B.safe_read(link)
            pipe=root/'pipe';os.mkfifo(pipe)
            with self.assertRaises(B.BackupError):B.safe_read(pipe)

    def test_memory_file_and_child_errors_never_print_payload(self):
        with B.memory_file() as output:
            B.stream_command(['/usr/bin/printf','synthetic'],subprocess.DEVNULL,output)
            output.seek(0);self.assertEqual(output.read(),b'synthetic')
        with B.memory_file() as output, self.assertRaisesRegex(B.BackupError,'details_withheld'):
            B.stream_command(['/bin/sh','-c','echo secret >&2; exit 9'],subprocess.DEVNULL,output)

    def test_process_timeout_is_bounded(self):
        with B.memory_file() as output, self.assertRaisesRegex(B.BackupError,'timeout'):
            B.stream_command(['/bin/sleep','30'],subprocess.DEVNULL,output,timeout=0)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        patch=mock.patch.object(B,'BACKUPS',Path(self.temp.name)/'backups');patch.start();self.addCleanup(patch.stop)
        self.local=types.SimpleNamespace(BASE=Path('/private'), PROJECT='local',check_state=mock.Mock(),
                                        runtime=mock.Mock(),directory=mock.Mock())
        self.engine=mock.Mock();self.engine.run.return_value=(0,b'')
        for name,value in [('table_inventory',mock.Mock(return_value=TABLES)),('payloads',mock.Mock(return_value=values()))]:
            patch=mock.patch.object(B,name,value);patch.start();self.addCleanup(patch.stop)
        self.public='age1'+'q'*58

    def execute(self):
        return B.backup(self.engine,self.local,LOCK,'rendered',{},Path('/age'),self.public)

    def test_dump_failure_resumes_services_and_removes_partial_file(self):
        with mock.patch.object(B,'stream_command',side_effect=B.BackupError('dump_failed')):
            with self.assertRaisesRegex(B.BackupError,'dump_failed'):self.execute()
        self.assertTrue(any('start' in call.args[0] for call in self.engine.run.call_args_list))
        self.assertEqual(list(B.BACKUPS.iterdir()),[])

    def test_partial_stop_failure_also_attempts_resume(self):
        self.engine.run.side_effect=[B.BackupError('stop_failed'),(0,b'')]
        with self.assertRaisesRegex(B.BackupError,'stop_failed'):self.execute()
        self.assertTrue(any('start' in call.args[0] for call in self.engine.run.call_args_list))

    def test_runtime_drift_stops_before_pause(self):
        self.local.runtime.side_effect=B.BackupError('drift')
        with self.assertRaisesRegex(B.BackupError,'drift'):self.execute()
        self.engine.run.assert_not_called()

    def test_success_publishes_private_ciphertext_only_after_resume(self):
        def stream(args,source,target,**kwargs):
            if 'pg_dump' in args:target.write(b'PGDMPsynthetic')
            else:
                self.assertTrue(any('start' in call.args[0] for call in self.engine.run.call_args_list))
                target.write(b'ciphertext')
        with mock.patch.object(B,'stream_command',side_effect=stream):result=self.execute()
        file=Path(result['backup_file']);self.assertEqual(file.read_bytes(),b'ciphertext')
        self.assertEqual(file.stat().st_mode&0o777,0o600)
        self.assertEqual(list(B.BACKUPS.glob('*.partial')),[])

    def test_failed_encryption_never_publishes_success_file(self):
        def stream(args,source,target,**kwargs):
            if 'pg_dump' in args:target.write(b'PGDMPsynthetic')
            else:target.write(b'partial');raise B.BackupError('encryption_failed')
        with mock.patch.object(B,'stream_command',side_effect=stream),self.assertRaises(B.BackupError):self.execute()
        self.assertEqual(list(B.BACKUPS.iterdir()),[])

    def test_restore_is_networkless_and_cleans_up_after_sql_failure(self):
        def stream(args,source,target,**kwargs):
            if '--decrypt' in args:target.write(B.pack(values(),LOCK,TABLES).getvalue())
            else:raise B.BackupError('restore_failed')
        with mock.patch.object(B,'safe_read',side_effect=[b'cipher',b'age-encryption.org/v1\nkey']),mock.patch.object(B,'stream_command',side_effect=stream):
            with self.assertRaisesRegex(B.BackupError,'restore_failed'):
                B.restore_sql(self.engine,LOCK,B.pack(values(),LOCK,TABLES))
        run=self.engine.run.call_args_list[0].args[0]
        self.assertEqual(run[run.index('--network')+1],'none')
        self.assertNotIn('--publish',run);self.assertNotIn('--volume',run)
        self.assertEqual(self.engine.run.call_args_list[-1].args[0][:3],['rm','--force','--volumes'])

    def test_restore_success_and_inventory_mismatch_both_clean_up(self):
        def stream(args,source,target,**kwargs):
            if '--decrypt' in args:target.write(B.pack(values(),LOCK,TABLES).getvalue())
        for inventory in (TABLES,'b'*32+'|42'):
            self.engine.reset_mock()
            with mock.patch.object(B,'safe_read',side_effect=[b'cipher',b'age-encryption.org/v1\nkey']),mock.patch.object(B,'stream_command',side_effect=stream),mock.patch.object(B,'table_inventory',return_value=inventory):
                if inventory==TABLES:
                    result=B.restore_sql(self.engine,LOCK,B.pack(values(),LOCK,TABLES))
                    self.assertEqual(result['status'],'passed')
                else:
                    with self.assertRaisesRegex(B.BackupError,'inventory_mismatch'):
                        B.restore_sql(self.engine,LOCK,B.pack(values(),LOCK,TABLES))
            self.assertEqual(self.engine.run.call_args_list[-1].args[0][:3],['rm','--force','--volumes'])

    def test_invalid_archive_never_launches_database(self):
        with self.assertRaises((B.BackupError,tarfile.ReadError)):
            B.restore_sql(self.engine,LOCK,io.BytesIO(b'invalid'))
        self.engine.run.assert_not_called()


class OwnerBoundaryTests(unittest.TestCase):
    def test_privileged_timeout_requests_cleanup_without_detaching_terminal(self):
        process=mock.Mock();process.poll.return_value=None
        with mock.patch.object(B.subprocess,'Popen',return_value=process) as launched, B.memory_file() as output:
            with self.assertRaisesRegex(B.BackupError,'timeout'):
                B.stream_command(['sudo','-n','synthetic-helper'],subprocess.DEVNULL,output,timeout=0,detached=False)
        self.assertFalse(launched.call_args.kwargs['start_new_session'])
        process.send_signal.assert_called_once_with(signal.SIGINT)
        process.wait.assert_called_once_with(timeout=75)
        process.kill.assert_not_called()

    def test_owner_controls_crypto_and_privileged_helpers_receive_no_key_or_phrase(self):
        self.run_owner(None)

    def test_bad_decryption_or_archive_stops_before_privileged_sql(self):
        for failure in ('decrypt','archive','root_result'):
            with self.subTest(stage=failure):self.run_owner(failure)

    def run_owner(self,failure):
        calls=[]
        def stream(args,source,target,**kwargs):
            calls.append((args,kwargs))
            if 'read-backup' in args:target.write(b'cipher')
            elif '--decrypt' in args:
                self.assertNotIn('sudo',args);self.assertTrue(kwargs['interactive'])
                if failure=='decrypt':raise B.BackupError('synthetic_crypto_failure')
                target.write(b'invalid' if failure=='archive' else B.pack(values(),LOCK,TABLES).getvalue())
            elif 'restore-sql' in args:
                self.assertFalse(kwargs.get('interactive',False));self.assertFalse(kwargs['detached'])
                self.assertNotIn('--identity',args);self.assertNotIn('--age',args)
                B.unpack(source,LOCK)
                report={'status':'passed','archive_integrity':'passed','isolated_sql_restore':'passed','cleanup':'completed',
                        'scope':B.RESTORE_SCOPE,'household_readiness':'pending'}
                if failure=='root_result':report['unexpected']='must reject'
                target.write(json.dumps(report).encode())
        with mock.patch.object(B.os,'geteuid',return_value=1000),mock.patch.object(B,'safe_read',return_value=b'age-encryption.org/v1\nkey'),mock.patch.object(B,'stream_command',side_effect=stream):
            if failure:
                with self.assertRaises((B.BackupError,tarfile.ReadError)):
                    B.restore_owner(LOCK,Path('/age'),Path('/backup'),Path('/identity'))
            else:
                self.assertEqual(B.restore_owner(LOCK,Path('/age'),Path('/backup'),Path('/identity'))['status'],'passed')
        if failure in ('decrypt','archive'):
            self.assertFalse(any('restore-sql' in args for args,_ in calls))

    def test_application_rehearsal_uses_the_same_unprivileged_crypto_boundary(self):
        rehearsal=B.rehearsal_module();seen=[]
        report={'status':'passed','ui_url':rehearsal.URL,'native_startup':'passed','restored_secret_signing':'passed',
                'restored_totp_readback':'passed','browser_evidence':{'new_login_event':False,'totp_step_advanced':False},
                'browser_acceptance':'pending_owner_confirmation','household_readiness':'pending','scope':rehearsal.SCOPE}
        def stream(args,source,target,**kwargs):
            seen.append(args)
            if 'read-backup' in args:target.write(b'cipher')
            elif '--decrypt' in args:
                self.assertNotIn('sudo',args);self.assertTrue(kwargs['interactive'])
                target.write(B.pack(values(),LOCK,TABLES).getvalue())
            elif 'rehearsal-load' in args:
                self.assertFalse(kwargs.get('interactive',False));B.unpack(source,LOCK)
                self.assertNotIn('--identity',args);target.write(json.dumps(report).encode())
            else:raise AssertionError(args)
        with mock.patch.object(B.os,'geteuid',return_value=1000),mock.patch.object(B,'safe_read',return_value=b'age-encryption.org/v1\nkey'),mock.patch.object(B,'stream_command',side_effect=stream):
            observed=B.restore_owner(LOCK,Path('/age'),Path('/backup'),Path('/identity'),application=True)
        self.assertEqual(observed,report)
        self.assertTrue(any('rehearsal-load' in args for args in seen))
        self.assertFalse(any('restore-sql' in args for args in seen))

    def test_root_cannot_prompt_as_owner(self):
        with mock.patch.object(B.os,'geteuid',return_value=0),self.assertRaisesRegex(B.BackupError,'desktop_user'):
            B.restore_owner(LOCK,Path('/age'),Path('/backup'),Path('/identity'))

    def test_privileged_ciphertext_reader_rejects_arbitrary_and_partial_paths(self):
        local=mock.Mock()
        for path in (Path('/etc/shadow'),B.BACKUPS/'identity-bad.age',B.BACKUPS/('identity-'+'a'*32+'.age.partial')):
            with self.assertRaisesRegex(B.BackupError,'fixed_private_backup_path'):
                B.export_ciphertext(local,path)
        local.ancestors.assert_not_called()

    def test_shell_restore_runs_owner_not_sudo_and_helpers_are_noninteractive(self):
        wrapper=(ROOT/'scripts/identity/backup.sh').read_text()
        branch=wrapper.split('if [[ "$mode" == restore-check || "$mode" == rehearsal-up ]]; then',1)[1].split('fi',1)[0]
        self.assertNotIn('sudo -n',branch)
        self.assertIn('"$mode" --age',branch)
        command=B.root_command('restore-sql')
        self.assertEqual(command[:2],['sudo','-n'])
        self.assertNotIn('--age',command);self.assertNotIn('--identity',command)


class KeyCustodyTests(unittest.TestCase):
    def test_shared_parent_rejected_before_key_creation(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.object(B.Path,'home',return_value=Path(home)):
            with self.assertRaisesRegex(B.BackupError,'unsafe_recovery_directory'):B.recovery_directory()
            self.assertFalse((Path(home)/'.config/agent-platform/recovery/identity.age').exists())

    def test_root_key_generation_is_rejected_before_files(self):
        with mock.patch.object(B.os,'geteuid',return_value=0),self.assertRaisesRegex(B.BackupError,'without_sudo'):
            B.key_create(Path('/age'))

    def test_encrypted_key_saved_without_plaintext_and_repeat_cannot_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            home=Path(temp);folder=home/'.config/agent-platform/recovery';folder.mkdir(parents=True,mode=0o700)
            def stream(args,source,target,**kwargs):
                if '-y' in args:target.write(('age1'+'q'*58).encode())
                elif '--passphrase' in args:target.write(b'age-encryption.org/v1\nsynthetic ciphertext')
                else:target.write(b'private synthetic marker')
            with mock.patch.object(B,'recovery_directory',return_value=folder),mock.patch.object(B,'stream_command',side_effect=stream):
                result=B.key_create(Path('/age'));file=Path(result['encrypted_identity'])
                self.assertNotIn(b'private synthetic marker',file.read_bytes())
                self.assertEqual(file.stat().st_mode&0o777,0o600)
                before=file.read_bytes()
                with self.assertRaisesRegex(B.BackupError,'no_overwrite'):B.key_create(Path('/age'))
                self.assertEqual(file.read_bytes(),before)

    def test_cancelled_encryption_removes_partial_key(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            home=Path(temp);folder=home/'.config/agent-platform/recovery';folder.mkdir(parents=True,mode=0o700)
            def stream(args,source,target,**kwargs):
                if '-y' in args:target.write(('age1'+'q'*58).encode())
                elif '--passphrase' in args:raise B.BackupError('cancelled')
                else:target.write(b'private synthetic marker')
            with mock.patch.object(B,'recovery_directory',return_value=folder),mock.patch.object(B,'stream_command',side_effect=stream):
                with self.assertRaises(B.BackupError):B.key_create(Path('/age'))
                self.assertFalse((home/'.config/agent-platform/recovery/identity.age').exists())


class TerminalPrivacyTests(unittest.TestCase):
    def test_background_terminal_rejected_before_reading_input(self):
        tty=mock.MagicMock();tty.fileno.return_value=42;tty.__enter__.return_value=tty
        with mock.patch('builtins.open',return_value=tty),mock.patch.object(B.os,'tcgetpgrp',return_value=-1):
            with self.assertRaisesRegex(B.BackupError,'not_foreground'):B.terminal_phrase()
        tty.readline.assert_not_called()

    def test_echo_failure_rejected_before_reading_and_original_settings_restored(self):
        tty=mock.MagicMock();tty.fileno.return_value=42;tty.__enter__.return_value=tty
        echo=[0,0,0,B.termios.ECHO|B.termios.ECHONL,0,0,[]]
        with mock.patch('builtins.open',return_value=tty),mock.patch.object(B.os,'tcgetpgrp',return_value=os.getpgrp()),mock.patch.object(B.termios,'tcgetattr',side_effect=[list(echo),list(echo),list(echo)]),mock.patch.object(B.termios,'tcsetattr') as setflags:
            with self.assertRaisesRegex(B.BackupError,'echo_not_disabled'):B.terminal_phrase()
        tty.readline.assert_not_called()
        self.assertEqual(setflags.call_args.args[2],echo)

    def test_empty_input_rejected_and_original_settings_restored(self):
        tty=mock.MagicMock();tty.fileno.return_value=42;tty.readline.return_value=b'\n';tty.__enter__.return_value=tty
        echo=[0,0,0,B.termios.ECHO|B.termios.ECHONL,0,0,[]];hidden=list(echo);hidden[3]=0
        with mock.patch('builtins.open',return_value=tty),mock.patch.object(B.os,'tcgetpgrp',return_value=os.getpgrp()),mock.patch.object(B.termios,'tcgetattr',side_effect=[list(echo),list(echo),hidden]),mock.patch.object(B.termios,'tcsetattr') as setflags,mock.patch.object(B.select,'select',return_value=([tty],[],[])):
            with self.assertRaisesRegex(B.BackupError,'nonempty'):B.terminal_phrase()
        self.assertEqual(setflags.call_args.args[2],echo)

    def test_stopped_crypto_child_fails_and_is_killed_reaped(self):
        stopped=(signal.SIGSTOP<<8)|0x7f
        with mock.patch.object(B.pty,'fork',return_value=(123,42)),mock.patch.object(B.select,'select',return_value=([],[],[])),mock.patch.object(B.os,'waitpid',side_effect=[(123,stopped),(123,signal.SIGKILL)]) as waited,mock.patch.object(B.os,'killpg') as killed,mock.patch.object(B.os,'close'):
            with self.assertRaisesRegex(B.BackupError,'process_stopped'):B.interactive_command(['/age'],None,None,20)
        killed.assert_called_once_with(123,signal.SIGKILL)
        self.assertEqual(waited.call_count,2)


class RewrapTests(unittest.TestCase):
    def test_rewrap_preserves_public_key_and_atomically_replaces_ciphertext(self):
        self.check_rewrap(None)

    def test_failed_unlock_encryption_or_verification_preserves_original(self):
        for failure in ('unlock','encrypt','verify','mismatch'):
            with self.subTest(stage=failure):self.check_rewrap(failure)

    def check_rewrap(self,failure):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);identity=folder/'identity.age';public=folder/'recipient.txt'
            original=b'age-encryption.org/v1\nold synthetic ciphertext'
            identity.write_bytes(original);identity.chmod(0o600)
            public.write_text('age1'+'q'*58+'\n');public.chmod(0o600)
            calls=0
            def stream(args,source,target,**kwargs):
                nonlocal calls
                calls+=1
                stage={1:'unlock',2:'public',3:'encrypt',4:'verify'}[calls]
                if stage==failure:raise B.BackupError('synthetic_failure')
                if stage in ('unlock','verify'):
                    target.write(b'wrong' if failure=='mismatch' and stage=='verify' else b'synthetic identity bytes')
                elif stage=='public':target.write(public.read_bytes())
                else:target.write(b'age-encryption.org/v1\nnew synthetic ciphertext')
            with mock.patch.object(B,'recovery_directory',return_value=folder),mock.patch.object(B,'stream_command',side_effect=stream):
                if failure:
                    with self.assertRaises(B.BackupError):B.key_rewrap(Path('/age'))
                    self.assertEqual(identity.read_bytes(),original)
                else:
                    report=B.key_rewrap(Path('/age'))
                    self.assertTrue(report['existing_backups_compatible'])
                    self.assertNotEqual(identity.read_bytes(),original)
                    self.assertEqual(identity.stat().st_mode&0o777,0o600)
                self.assertEqual(public.read_text(),'age1'+'q'*58+'\n')
                self.assertEqual(list(folder.glob('*.partial')),[])


class NativeCryptoTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'),'mise age tools required')
    def test_real_encrypted_key_prompts_and_proc_fd_decryption(self):
        # A disposable PTY exercises the same native /dev/tty prompts as the owner.
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);age=Path(shutil.which('age'))
            pid,terminal=pty.fork()
            if pid==0:
                try:
                    with mock.patch.object(B,'recovery_directory',return_value=folder):
                        B.key_create(age)
                    public=(folder/'recipient.txt').read_text().strip()
                    cipher=subprocess.run([str(age),'-r',public],input=b'synthetic secret payload',capture_output=True,check=True).stdout
                    with B.memory_file() as encrypted,B.memory_file() as key,B.memory_file() as plain:
                        encrypted.write(cipher);encrypted.seek(0)
                        key.write((folder/'identity.age').read_bytes());key.seek(0)
                        key_path='/proc/'+str(os.getpid())+'/fd/'+str(key.fileno())
                        B.stream_command([str(age),'--decrypt','--identity',key_path],encrypted,plain,interactive=True,timeout=20)
                        plain.seek(0)
                        if plain.read()!=b'synthetic secret payload':os._exit(3)
                    with mock.patch.object(B,'recovery_directory',return_value=folder):
                        B.key_rewrap(age)
                    with B.memory_file() as encrypted,B.memory_file() as key,B.memory_file() as plain:
                        encrypted.write(cipher);encrypted.seek(0)
                        key.write((folder/'identity.age').read_bytes());key.seek(0)
                        key_path='/proc/'+str(os.getpid())+'/fd/'+str(key.fileno())
                        B.stream_command([str(age),'--decrypt','--identity',key_path],encrypted,plain,interactive=True,timeout=20)
                        plain.seek(0)
                        if plain.read()!=b'synthetic secret payload':os._exit(4)
                    os._exit(0)
                except BaseException:os._exit(2)
            buffer=b'';observed=b'';prompts=0;status=None;deadline=time.monotonic()+45
            try:
                while time.monotonic()<deadline:
                    ready,_,_=select.select([terminal],[],[],0.1)
                    if ready:
                        try:data=os.read(terminal,4096)
                        except OSError:data=b''
                        buffer+=data;observed+=data
                        if b'passphrase' in buffer.lower() and buffer.rstrip().endswith(b':'):
                            prompts+=1
                            if prompts>8:break
                            phrase=b'synthetic-old-test-phrase' if prompts<=4 else b'synthetic-new-test-phrase'
                            os.write(terminal,phrase+b'\n');buffer=b''
                    done,value=os.waitpid(pid,os.WNOHANG)
                    if done:status=value;break
                self.assertIsNotNone(status,'Interactive crypto child timed out; no private output is included')
                self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0,'Native encrypted identity/PTY recovery failed')
                self.assertEqual(prompts,8)
                self.assertNotIn(b'synthetic-old-test-phrase',observed)
                self.assertNotIn(b'synthetic-new-test-phrase',observed)
            finally:
                if status is None:
                    os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
                os.close(terminal)

    def test_real_age_round_trip_wrong_key_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            key=Path(temp)/'synthetic.agekey';other=Path(temp)/'wrong.agekey'
            for file in (key,other):
                subprocess.run(['age-keygen','-o',str(file)],check=True,capture_output=True)
            public=subprocess.run(['age-keygen','-y',str(key)],check=True,capture_output=True).stdout.decode().strip()
            B.recipient(public)
            cipher=subprocess.run(['age','-r',public],input=b'synthetic backup bytes',check=True,capture_output=True).stdout
            self.assertNotIn(b'synthetic backup bytes',cipher)
            plain=subprocess.run(['age','-d','-i',str(key)],input=cipher,check=True,capture_output=True).stdout
            self.assertEqual(plain,b'synthetic backup bytes')
            for data,identity in ((cipher,other),(cipher[:-5]+b'xxxxx',key)):
                result=subprocess.run(['age','-d','-i',str(identity)],input=data,capture_output=True)
                self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
