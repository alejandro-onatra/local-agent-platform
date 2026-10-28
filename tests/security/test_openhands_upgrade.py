"""Verify upgrade isolation and backup-before-recreation ordering without Docker."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('upgrade',ROOT/'scripts/openhands/upgrade.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class FakeEngine:
    def __init__(self):
        self.events=[]
        self.identity='10001:10001'
        self.fail_at=None
        self.info={'running':True,'image':'sha256:synthetic','labels':{'com.docker.compose.project':module.PROJECT,'com.docker.compose.service':'openhands'},'mounts':[
            {'Destination':'/home/openhands/.openhands','Type':'volume','Name':module.STATE},
            {'Destination':'/projects','Type':'bind','Source':str(module.ROOT/'artifacts/openhands/projects')}]}
        self.digests=['new@sha256:'+'a'*64]

    def pull(self,image,timeout=1800):
        return self.d("pull",image)

    def d(self,*args,**kwargs):
        self.events.append(('docker',args))
        if self.fail_at and self.fail_at in args:raise module.UpgradeError('Synthetic Docker failure')
        if args[0]=='inspect':return json.dumps(self.info).encode()
        if args[:2]==('image','inspect'):return json.dumps(self.digests).encode()
        if '-c' in args:return self.identity.encode()
        if kwargs.get('output') is not None:
            with tarfile.open(fileobj=kwargs['output'],mode='w') as archive:
                info=tarfile.TarInfo('synthetic.txt');info.size=1;archive.addfile(info,io.BytesIO(b'x'))
        return b''

    def c(self,*args):
        self.events.append(('compose',args))
        if self.fail_at and self.fail_at in args:raise module.UpgradeError('Synthetic Compose failure')
        if 'ps' in args:return ('a'*64).encode()
        return b''


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.engine=FakeEngine()
        self.lock={'image':'new@sha256:'+'a'*64,'upgrade_from':{'image':'old@sha256:'+'b'*64}}
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def apply(self):
        with patch.dict(os.environ,OH_HOST_GID='1000'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
            module.apply(self.engine,self.lock,'helper@sha256:'+'c'*64,10001,10001,self.engine.info,module.ROOT/'artifacts/openhands/projects',self.base)

    def test_identity_and_exact_mounts_are_required(self):
        module.selected_container(self.engine,self.lock)
        module.safe_backup_sources(self.engine.info)
        self.engine.info['labels']['com.docker.compose.project']='other'
        with self.assertRaises(module.UpgradeError):module.selected_container(self.engine,self.lock)
        self.engine.info['mounts'][0]['Name']='other-state'
        with self.assertRaises(module.UpgradeError):module.safe_backup_sources(self.engine.info)

    def test_unknown_image_and_private_workspace_are_rejected(self):
        self.engine.digests=['unrelated-image']
        with self.assertRaises(module.UpgradeError):module.selected_container(self.engine,self.lock)
        self.engine.info['mounts'][1]['Source']='/home/private-folder'
        with self.assertRaises(module.UpgradeError):module.safe_backup_sources(self.engine.info)

    def test_candidate_is_isolated_and_never_mounts_existing_state(self):
        with contextlib.redirect_stdout(io.StringIO()):module.preflight(self.engine,self.lock,10001,10001)
        probes=[args for kind,args in self.engine.events if args[0]=='run']
        self.assertEqual(len(probes),2)
        for args in probes:
            self.assertIn('--read-only',args)
            self.assertEqual(args[args.index('--network')+1],'none')
            self.assertEqual(args[args.index('--cap-drop')+1],'ALL')
            self.assertNotIn('--mount',args)
            self.assertIn('no-new-privileges:true',args)
        self.assertFalse(any(kind=='compose' for kind,args in self.engine.events))

    def test_candidate_uid_change_blocks_runtime_and_stop(self):
        self.engine.identity='2000:2000'
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(module.UpgradeError):module.preflight(self.engine,self.lock,10001,10001)
        self.assertEqual(sum(args[0]=='run' for kind,args in self.engine.events),1)
        self.assertFalse(any(kind=='compose' for kind,args in self.engine.events))

    def test_success_stops_and_backs_up_before_recreation(self):
        self.apply()
        events=self.engine.events
        stop=next(i for i,e in enumerate(events) if e==('compose',('stop','openhands','openhands-proxy')))
        archive=[i for i,(kind,args) in enumerate(events) if '-cf' in args]
        up=next(i for i,(kind,args) in enumerate(events) if kind=='compose' and 'up' in args)
        self.assertTrue(stop<min(archive)<max(archive)<up)
        folders=list(self.base.glob('openhands-*'));self.assertEqual(len(folders),1)
        for name in ['state.tar','projects.tar','manifest.json']:
            self.assertEqual((folders[0]/name).stat().st_mode & 0o777,0o600)
        self.assertFalse(any('down' in args or '-v' in args for kind,args in events))

    def test_backup_failure_restarts_old_containers_without_recreation(self):
        self.engine.fail_at='-cf'
        with self.assertRaises(module.UpgradeError):self.apply()
        calls=[args for kind,args in self.engine.events if kind=='compose']
        self.assertIn(('start','openhands','openhands-proxy'),calls)
        self.assertFalse(any('up' in args for args in calls))

    def test_backup_failure_does_not_start_a_previously_stopped_deployment(self):
        self.engine.info['running']=False
        self.engine.fail_at='-cf'
        with self.assertRaises(module.UpgradeError):self.apply()
        self.assertFalse(any(kind=='compose' and 'start' in args for kind,args in self.engine.events))

    def test_health_failure_stops_candidate_without_automatic_state_restore(self):
        with patch.dict(os.environ,OH_HOST_GID='1000'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(module.subprocess,'run',side_effect=[SimpleNamespace(returncode=0),SimpleNamespace(returncode=0),SimpleNamespace(returncode=1)]),self.assertRaises(module.UpgradeError):
            module.apply(self.engine,self.lock,'helper-image',10001,10001,self.engine.info,module.ROOT/'artifacts/openhands/projects',self.base)
        self.assertEqual(self.engine.events[-1],('compose',('stop','openhands','openhands-proxy')))

    def test_invalid_archive_blocks_recreation_and_restarts_existing_services(self):
        with patch.dict(os.environ,OH_HOST_GID='1000'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=1)),self.assertRaises(module.UpgradeError):
            module.apply(self.engine,self.lock,'helper-image',10001,10001,self.engine.info,module.ROOT/'artifacts/openhands/projects',self.base)
        self.assertEqual(self.engine.events[-1],('compose',('start','openhands','openhands-proxy')))
        self.assertFalse(any(kind=='compose' and 'up' in args for kind,args in self.engine.events))

    def test_partial_recreation_failure_stops_candidate_and_keeps_backup(self):
        self.engine.fail_at='up'
        with self.assertRaises(module.UpgradeError):self.apply()
        calls=[args for kind,args in self.engine.events if kind=='compose']
        self.assertEqual(calls[-1],('stop','openhands','openhands-proxy'))
        self.assertFalse(any('start' in args for args in calls))
        self.assertTrue(next(self.base.glob('openhands-*')).joinpath('manifest.json').exists())

    def test_symlinked_backup_path_is_rejected(self):
        (self.base/'linked').symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(module.UpgradeError):module.private_directory(self.base/'linked')

    def test_guard_up_compose_does_not_require_unset_hardening_identity(self):
        with patch.dict(os.environ,{'OH_ISOLATED_USER':''}):
            engine=module.Engine()
        self.assertFalse(any('hardening.yaml' in arg for arg in engine.compose))


if __name__=='__main__':unittest.main()
