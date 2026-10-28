"""Storage guards must fail on wrong identities/mounts; simulated setup is not live acceptance."""
import copy
import contextlib
import errno
import io
import shutil
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock
import yaml

ROOT=Path(__file__).resolve().parents[2]
def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/storage'/filename)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result)
    return result
STORE=module('pilot_storage','storage.py')
ACCEPT=module('pilot_acceptance','acceptance.py')


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy=STORE.load_policy()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'policy.yaml'

    def mutated(self,change):
        policy=copy.deepcopy(self.policy);change(policy)
        self.path.write_text(yaml.safe_dump(policy))
        with self.assertRaises(STORE.StorageError): STORE.load_policy(self.path)

    def test_exact_synthetic_budget_and_distinct_paths(self):
        selected=STORE.entries(self.policy)
        self.assertEqual(sum(e[2] for e in selected),512*STORE.MIB)
        self.assertEqual(len({e[3] for e in selected}),4)
        self.assertEqual(len({e[4] for e in selected}),4)
        self.assertEqual({e[4].parent.name for e in selected},{'probe-a','probe-b'})

    def test_identity_duplicates_traversal_root_and_real_names_rejected(self):
        for change in [lambda p:p['tenants'][1].update(id='probe-a'),
                       lambda p:p['tenants'][1].update(uid=200001,gid=200001),
                       lambda p:p['tenants'][0].update(id='../escape'),
                       lambda p:p['tenants'][0].update(id='family'),
                       lambda p:p['tenants'][0].update(uid=0,gid=0),
                       lambda p:p['tenants'][0].update(uid=True,gid=True),
                       lambda p:p['tenants'][0].update(gid=200010)]:
            self.mutated(change)

    def test_budget_expansion_low_reserve_or_path_override_rejected(self):
        for change in [lambda p:p['volumes_mib'].update(workspace=1024),
                       lambda p:p['volumes_mib'].update(workspace=True),
                       lambda p:p.update(host_reserve_gib=0),
                       lambda p:p.update(root='/home/person/CloudDrive'),
                       lambda p:p.update(purpose='production')]:
            self.mutated(change)

    def test_duplicate_yaml_keys_and_linked_input_fail(self):
        self.path.write_text('schema_version: 1\nschema_version: 1\n')
        with self.assertRaises(STORE.StorageError): STORE.load_policy(self.path)
        self.path.unlink();self.path.symlink_to(ROOT/'config/storage/pilot.yaml')
        with self.assertRaises(STORE.StorageError): STORE.load_policy(self.path)

    def test_host_identity_collision_blocks_preparation(self):
        with mock.patch.object(STORE.pwd,'getpwuid',return_value=object()):
            with self.assertRaises(STORE.StorageError): STORE.require_unused_ids(self.policy)
        with mock.patch.object(STORE.pwd,'getpwuid',side_effect=KeyError), \
                mock.patch.object(STORE.grp,'getgrgid',return_value=object()):
            with self.assertRaises(STORE.StorageError): STORE.require_unused_ids(self.policy)

    def test_capacity_retains_host_reserve(self):
        with mock.patch.object(STORE.shutil,'disk_usage',return_value=types.SimpleNamespace(free=20*STORE.GIB)):
            self.assertFalse(STORE.available_capacity(self.policy)[2])
        with mock.patch.object(STORE.shutil,'disk_usage',return_value=types.SimpleNamespace(free=21*STORE.GIB)):
            self.assertTrue(STORE.available_capacity(self.policy)[2])

    def test_unsupported_backing_filesystem_blocks_plan(self):
        with mock.patch.object(STORE,'backing_filesystem',return_value='btrfs'):
            with self.assertRaisesRegex(STORE.StorageError,'unsupported_backing_filesystem'):
                STORE.plan(self.policy)

    def test_plan_observes_capacity_without_allocating(self):
        with mock.patch.object(STORE,'backing_filesystem',return_value='ext4'), \
                mock.patch.object(STORE,'available_capacity',return_value=(512*STORE.MIB,30*STORE.GIB,True)), \
                mock.patch.object(STORE,'require_unused_ids'),mock.patch.object(STORE,'prepare') as prepare:
            result=STORE.plan(self.policy)
        self.assertEqual(result['backing_filesystem'],'ext4')
        self.assertEqual(result['host_setup'],'pending')
        prepare.assert_not_called()


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.entry=STORE.entries(STORE.load_policy())[0]
        self.target=self.entry[4]
        self.engine=mock.Mock()
        self.engine.mount_info.return_value={'target':str(self.target),'source':'/dev/loop77',
            'fstype':'ext4','options':'rw,relatime,nodev,nosuid,noexec'}
        self.engine.backing_file.return_value=str(self.entry[3])
        self.details=types.SimpleNamespace(st_uid=self.entry[0]['uid'],st_gid=self.entry[0]['gid'],
                                          st_mode=stat.S_IFDIR|0o700)
        self.fs=types.SimpleNamespace(f_blocks=30000,f_frsize=4096)

    def verify(self):
        with mock.patch.object(STORE,'safe_path'),mock.patch.object(STORE,'safe_image'), \
                mock.patch.object(STORE.Path,'lstat',return_value=self.details), \
                mock.patch.object(STORE.os,'statvfs',return_value=self.fs):
            return STORE.verify_mount(self.entry,self.engine)

    def test_expected_mount_is_accepted_but_not_family_ready(self):
        self.assertEqual(self.verify()['status'],'passed')

    def test_unmounted_directory_never_falls_back_to_host_disk(self):
        self.engine.mount_info.return_value=None
        with self.assertRaises(STORE.StorageError) as caught:self.verify()
        self.assertEqual(str(caught.exception),'required_mount_missing')

    def test_wrong_source_parent_target_fstype_and_missing_flags_fail(self):
        original=copy.deepcopy(self.engine.mount_info.return_value)
        for field,value in [('target','/'),('fstype','tmpfs'),('options','rw,nodev,nosuid'),
                            ('options','rw,nodev,nosuid,noexec,discard')]:
            self.engine.mount_info.return_value=original|{field:value}
            with self.subTest(field=field),self.assertRaises(STORE.StorageError):self.verify()
        self.engine.mount_info.return_value=original
        self.engine.backing_file.return_value='/other.ext4'
        with self.assertRaises(STORE.StorageError):self.verify()

    def test_cross_uid_world_readable_or_capacity_expansion_rejected(self):
        original=copy.copy(self.details)
        for field,value in [('st_uid',200002),('st_gid',200002),('st_mode',stat.S_IFDIR|0o755)]:
            self.details=copy.copy(original);setattr(self.details,field,value)
            with self.assertRaises(STORE.StorageError):self.verify()
        self.details=original;self.fs.f_blocks=100000
        with self.assertRaises(STORE.StorageError):self.verify()

    def test_backing_file_device_symlink_hardlink_sparse_and_wrong_size_fail(self):
        good=types.SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_uid=0,st_nlink=1,
                                   st_size=128*STORE.MIB,st_blocks=128*STORE.MIB//512)
        with mock.patch.object(STORE.Path,'lstat',return_value=good):
            STORE.safe_image(Path('/synthetic'),128*STORE.MIB)
        for field,value in [('st_mode',stat.S_IFBLK|0o600),('st_mode',stat.S_IFLNK|0o600),
                            ('st_mode',stat.S_IFREG|0o644),('st_uid',1000),('st_nlink',2),
                            ('st_size',256*STORE.MIB),('st_blocks',0)]:
            bad=copy.copy(good);setattr(bad,field,value)
            with mock.patch.object(STORE.Path,'lstat',return_value=bad), \
                    self.assertRaises(STORE.StorageError):STORE.safe_image(Path('/synthetic'),128*STORE.MIB)

    def test_managed_ancestor_must_not_be_linked_or_writable_by_tenant(self):
        for mode,uid in [(stat.S_IFLNK|0o700,0),(stat.S_IFDIR|0o777,0),(stat.S_IFDIR|0o700,200001)]:
            with mock.patch.object(STORE.Path,'lstat',return_value=types.SimpleNamespace(st_mode=mode,st_uid=uid)), \
                    self.assertRaises(STORE.StorageError):STORE.safe_path(STORE.BASE)

    def test_loop_device_probe_rejects_arbitrary_block_device(self):
        with self.assertRaises(STORE.StorageError):STORE.Engine().backing_file('/dev/sda')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'managed'/'pilot'
        self.policy=STORE.load_policy();self.engine=mock.Mock()
        self.engine.mount_info.return_value=None
        for name in ('safe_path','safe_image','require_unused_ids','verify_mount','reserve_image'):
            patch=mock.patch.object(STORE,name);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(STORE.os,'posix_fallocate');self.allocate=patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(STORE,'available_capacity',return_value=(512*STORE.MIB,30*STORE.GIB,True));patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(STORE.os,'chown');patch.start();self.addCleanup(patch.stop)

    def test_new_setup_allocates_before_formatting_only_new_files(self):
        result=STORE.prepare(self.policy,self.engine,self.base)
        self.assertEqual(result['status'],'prepared');self.assertEqual(self.allocate.call_count,4)
        formats=[call.args[0] for call in self.engine.run.call_args_list if call.args[0][0]=='mkfs.ext4']
        self.assertEqual(len(formats),4)
        self.assertTrue(all(str(self.base/'images') in command[-1] for command in formats))
        self.assertTrue(all('nodiscard,lazy_itable_init=0,lazy_journal_init=0' in command for command in formats))
        self.assertTrue((self.base/'record.yaml').is_file())

    def test_existing_incomplete_tree_is_preserved_and_never_formatted(self):
        self.base.mkdir(parents=True);marker=self.base/'private.txt';marker.write_text('synthetic-existing')
        with self.assertRaises(STORE.StorageError):STORE.prepare(self.policy,self.engine,self.base)
        self.assertEqual(marker.read_text(),'synthetic-existing');self.engine.run.assert_not_called()

    def test_completed_existing_images_are_never_reformatted_or_reallocated(self):
        STORE.prepare(self.policy,self.engine,self.base)
        self.engine.reset_mock();self.allocate.reset_mock()
        with mock.patch.object(STORE,'inspect_record'):
            STORE.prepare(self.policy,self.engine,self.base)
        self.allocate.assert_not_called()
        self.assertFalse(any(c.args[0][0]=='mkfs.ext4' for c in self.engine.run.call_args_list))

    def test_allocation_failure_preserves_partial_files_and_never_mounts(self):
        self.allocate.side_effect=OSError('synthetic-sensitive-marker')
        with self.assertRaises(OSError):STORE.prepare(self.policy,self.engine,self.base)
        self.engine.run.assert_not_called();self.assertFalse((self.base/'record.yaml').exists())
        self.assertTrue(self.base.is_dir())

    def test_low_capacity_prevents_any_allocation(self):
        with mock.patch.object(STORE,'available_capacity',return_value=(1,0,False)):
            with self.assertRaises(STORE.StorageError):STORE.prepare(self.policy,self.engine,self.base)
        self.assertFalse(self.base.exists());self.allocate.assert_not_called()

    def test_unmount_preserves_images_and_never_forces_busy_mounts(self):
        self.engine.mount_info.return_value={'synthetic':'mounted'}
        with mock.patch.object(STORE,'inspect_record'):
            result=STORE.unmount(self.policy,self.engine,self.base)
        self.assertTrue(result['images_preserved'])
        self.assertTrue(all(c.args[0][0]=='umount' and len(c.args[0])==2 for c in self.engine.run.call_args_list))


class AcceptanceTests(unittest.TestCase):
    def test_probe_has_no_network_root_capabilities_or_unbounded_resources(self):
        tenant={'uid':200001,'gid':200001}
        command=ACCEPT.docker_command(STORE,'pinned-image',tenant,'workspace',128*STORE.MIB,
                                     Path('/one/workspace'),Path('/one/state'),Path('/two/workspace'),'.synthetic','unique')
        self.assertIn('--read-only',command)
        for option,value in [('--network','none'),('--user','200001:200001'),('--cap-drop','ALL'),
                             ('--memory','256m'),('--pids-limit','64'),('--log-driver','none')]:
            self.assertEqual(command[command.index(option)+1],value)
        self.assertFalse(any('docker.sock' in arg for arg in command))
        self.assertIn('type=bind,src=/two/workspace,dst=/other,readonly',command)

    def test_any_failed_missing_or_fake_probe_result_fails(self):
        good={key:True for key in ACCEPT.CHECKS}|{'written_mib':120}
        self.assertTrue(ACCEPT.valid_result(good))
        for key in ACCEPT.CHECKS:
            self.assertFalse(ACCEPT.valid_result(good|{key:False}))
            self.assertFalse(ACCEPT.valid_result(good|{key:'passed'}))
        self.assertFalse(ACCEPT.valid_result({}))
        self.assertFalse(ACCEPT.valid_result(good|{'written_mib':float('nan')}))
        self.assertFalse(ACCEPT.valid_result(good|{'written_mib':999}))

    def test_nonempty_pilot_is_not_used_for_fill_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory);(target/'private.txt').write_text('synthetic')
            with self.assertRaises(STORE.StorageError):
                ACCEPT.require_synthetic_only(STORE,[(None,None,None,None,target)])
            self.assertEqual((target/'private.txt').read_text(),'synthetic')

    def orchestrate(self,failed=False):
        policy=STORE.load_policy()
        with tempfile.TemporaryDirectory() as directory:
            selected=STORE.entries(policy,Path(directory))
            for entry in selected:entry[4].mkdir(parents=True)
            api=types.SimpleNamespace(check=mock.Mock(),entries=lambda p:selected,
                read_yaml=STORE.read_yaml,ROOT=ROOT,StorageError=STORE.StorageError)
            engine=mock.Mock();good={key:True for key in ACCEPT.CHECKS}|{'written_mib':120}
            image=STORE.read_yaml(ROOT/'infra/openhands/versions.yaml')['image']
            def run(command,**kwargs):
                if 'inspect' in command:return json.dumps([image]).encode()
                if 'run' in command:
                    return json.dumps(good|({'disk_full_denied':False} if failed else {})).encode()
                return b''
            engine.run.side_effect=run
            with mock.patch('os.fchown'),contextlib.redirect_stderr(io.StringIO()):
                if failed:
                    with self.assertRaises(STORE.StorageError):ACCEPT.accept(policy,engine,api)
                    result=None
                else:result=ACCEPT.accept(policy,engine,api)
            self.assertTrue(all(not list(entry[4].iterdir()) for entry in selected))
            runs=[c.args[0] for c in engine.run.call_args_list if 'run' in c.args[0]]
            removals=[c.args[0] for c in engine.run.call_args_list if 'rm' in c.args[0]]
            self.assertEqual(len(runs),len(removals))
            return result,runs

    def test_acceptance_checks_both_users_both_volumes_and_stays_pending(self):
        result,runs=self.orchestrate()
        self.assertEqual(len(runs),4)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['household_readiness'],'pending')

    def test_failed_docker_probe_cleans_canaries_and_stops_acceptance(self):
        result,runs=self.orchestrate(failed=True)
        self.assertEqual(len(runs),1)

    def test_cli_accept_dispatches_the_same_api_and_does_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'pilot';lock=base.parent/'storage-pilot.lock'
            lock.touch(mode=0o600)
            details=types.SimpleNamespace(st_uid=0,st_nlink=1,st_mode=stat.S_IFREG|0o600)
            accepted=mock.Mock(return_value={'status':'passed','household_readiness':'pending'})
            with mock.patch.dict(sys.modules,{'acceptance':types.SimpleNamespace(accept=accepted)}), \
                    mock.patch.object(sys,'argv',['storage.py','accept']), \
                    mock.patch.object(STORE,'BASE',base),mock.patch.object(STORE,'safe_path'), \
                    mock.patch.object(STORE.os,'geteuid',return_value=0), \
                    mock.patch.object(STORE,'backing_filesystem',return_value='ext4'), \
                    mock.patch.object(STORE.os,'fstat',return_value=details), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(STORE.main(),0)
            self.assertIs(accepted.call_args.args[2],STORE)
            self.assertFalse(base.exists())

    def execute_probe(self,error):
        with tempfile.TemporaryDirectory() as directory:
            own=Path(directory)/'own';other=Path(directory)/'other'
            own.mkdir();other.mkdir()
            (own/'.canary').write_text('synthetic storage canary')
            (other/'.canary').write_text('synthetic storage canary')
            real_path=Path
            real_open=open
            real_path_open=Path.open
            class Writer:
                count=0
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def write(self,data):
                    self.count+=1
                    if error is not None and self.count>2:raise OSError(error,'synthetic')
                    return len(data)
                def fileno(self):return 1
            def path(value):
                return real_path({'/projects':str(own),'/other':str(other)}.get(str(value),value))
            def writer(file,*args,**kwargs):
                if file.name.startswith('.quota-probe-'):
                    file.touch(exist_ok=False)
                    return Writer()
                return real_path_open(file,*args,**kwargs)
            def read(file,*args,**kwargs):
                if str(file)==str(other/'.canary'):raise PermissionError('synthetic')
                return real_open(file,*args,**kwargs)
            output=io.StringIO()
            with mock.patch('pathlib.Path',side_effect=path), \
                    mock.patch.object(real_path,'open',new=writer), \
                    mock.patch('builtins.open',side_effect=read), \
                    mock.patch.object(sys,'argv',['probe','workspace',str(STORE.MIB),
                                                  '/unmounted/host-canary',str(os.getuid()),'.canary']), \
                    mock.patch('os.fsync'),contextlib.redirect_stdout(output):
                if error is not None and error!=errno.ENOSPC:
                    with self.assertRaises(OSError):exec(ACCEPT.PROBE,{})
                    result=None
                else:
                    exec(ACCEPT.PROBE,{})
                    result=json.loads(output.getvalue())
            self.assertFalse(list(own.glob('.quota-probe-*')))
            return result

    def test_enospc_accepts_denials_and_removes_only_probe_file(self):
        result=self.execute_probe(errno.ENOSPC)
        self.assertTrue(ACCEPT.valid_result(result))

    def test_no_enospc_cannot_pass_capacity_test(self):
        result=self.execute_probe(None)
        self.assertFalse(result['disk_full_denied'])
        self.assertFalse(ACCEPT.valid_result(result))

    def test_unrelated_write_error_fails_and_cleans_scratch(self):
        self.execute_probe(errno.EIO)

    @unittest.skipUnless(shutil.which('mkfs.ext4'),'Host e2fsprogs required')
    def test_real_new_regular_image_reserves_capacity_again_after_format(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'synthetic.ext4';size=128*STORE.MIB
            fd=os.open(image,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:os.posix_fallocate(fd,0,size)
            finally:os.close(fd)
            STORE.Engine().run(['mkfs.ext4','-q','-F','-m','0','-E',
                               'nodiscard,lazy_itable_init=0,lazy_journal_init=0',str(image)],timeout=60)
            STORE.reserve_image(image,size,owner=os.getuid())
            STORE.safe_image(image,size,owner=os.getuid())


if __name__=='__main__':unittest.main()
