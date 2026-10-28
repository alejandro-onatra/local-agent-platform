"""Exercise shell plan/apply/rollback with a bounded fake Docker, not live services."""
import json
import os
import pty
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name)/'repo';self.repo.mkdir()
        for name in ['scripts/llm/common.sh','scripts/openhands/common.sh','scripts/openhands/hardening.sh',
                     'scripts/openhands/hardening-settings.py','scripts/openhands/start-agent-server.py','infra/openhands/versions.yaml']:
            target=self.repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        (self.repo/'scripts/openhands/check.sh').write_text('#!/usr/bin/env bash\nexit 1\n')
        self.bin=Path(self.temp.name)/'bin';self.bin.mkdir()
        self.log=Path(self.temp.name)/'docker-commands.jsonl'
        fake=self.bin/'docker'
        fake.write_text('''#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')
a=args[2:] if args[:2]==['--context','default'] else args
if a[0]=='info':raise SystemExit(0)
if a[0]=='inspect':
 if '{{.State.Running}}' in a:print(os.environ.get('FAKE_RUNNING','true'))
 else:print('sha256:synthetic-image')
 raise SystemExit(0)
if a[:2]==['image','inspect']:
 print(json.dumps(['ghcr.io/openhands/agent-canvas@sha256:ce4526401c08b47d74fd0be5ebf97e8219d6a02955cb6710e8cc3335f01291a6']));raise SystemExit(0)
if a[0]=='compose':
 if 'ps' in a:print('synthetic-container');raise SystemExit(0)
 if 'exec' in a:
  if '--runtime-check' in a:
   raise SystemExit(int(os.environ.get('FAKE_RUNTIME_FAILURE','0')))
  if os.environ.get('FAKE_REQUIRE_CLOSED_INPUT')=='1':
   if '--interactive=false' not in a or os.isatty(0):raise SystemExit(86)
   if os.read(0,1)!=b'':raise SystemExit(87)
  print(os.environ.get('FAKE_IDENTITY','1000:1000'));raise SystemExit(0)
 if 'config' in a or 'up' in a:raise SystemExit(0)
raise SystemExit(99)
''');fake.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],FAKE_LOG=str(self.log))

    def command(self,mode,stdin=None):
        return subprocess.run(['bash',str(self.repo/'scripts/openhands/hardening.sh'),mode],
                              env=self.env,stdin=stdin,text=True,capture_output=True,timeout=20)

    def test_plan_does_not_create_record_or_recreate_services(self):
        p=self.command('plan');self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())
        self.assertFalse(any('up' in json.loads(line) for line in self.log.read_text().splitlines()))

    def test_identity_probe_ignores_terminal_input(self):
        self.env['FAKE_REQUIRE_CLOSED_INPUT']='1'
        master,slave=pty.openpty()
        try:
            self.assertTrue(os.isatty(slave))
            p=self.command('plan',stdin=slave)
        finally:
            os.close(slave);os.close(master)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('without interactive input',p.stdout)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())

    def test_missing_python_module_blocks_apply_before_recreation(self):
        self.env['FAKE_RUNTIME_FAILURE']='1'
        p=self.command('apply');self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())
        calls=[json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertFalse(any('up' in args for args in calls))

    def test_stopped_container_cannot_plan_or_activate(self):
        self.env['FAKE_RUNNING']='false'
        p=self.command('plan');self.assertNotEqual(p.returncode,0)
        self.assertIn('exists but is not running',p.stderr)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())
        calls=[json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertFalse(any('exec' in args or 'up' in args for args in calls))
        self.assertTrue(any('--all' in args for args in calls if 'ps' in args))

    def test_unverified_root_identity_cannot_apply(self):
        self.env['FAKE_IDENTITY']='0:0';p=self.command('apply')
        self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())
        self.assertFalse(any('up' in json.loads(line) for line in self.log.read_text().splitlines()))

    def test_failed_health_restores_previous_profile_without_deleting_data(self):
        p=self.command('apply');self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.repo/'artifacts/openhands/hardening.yaml').exists())
        calls=[json.loads(line) for line in self.log.read_text().splitlines()]
        up=[args for args in calls if 'up' in args]
        self.assertEqual(len(up),2)
        self.assertTrue(any(item.endswith('/infra/openhands/hardening.yaml') for item in up[0]))
        self.assertFalse(any(item.endswith('/infra/openhands/hardening.yaml') for item in up[1]))
        self.assertFalse(any('down' in args or 'rm' in args for args in calls))

    def test_successful_apply_records_verified_identity_and_later_plan_uses_it_once(self):
        (self.repo/'scripts/openhands/check.sh').write_text('#!/usr/bin/env bash\nexit 0\n')
        p=self.command('apply');self.assertEqual(p.returncode,0,p.stderr)
        record=self.repo/'artifacts/openhands/hardening.yaml'
        self.assertEqual(record.read_text(),'schema_version: 1\nuid: 1000\ngid: 1000\n')
        self.assertEqual(record.stat().st_mode & 0o777,0o600)
        self.log.write_text('');p=self.command('plan');self.assertEqual(p.returncode,0,p.stderr)
        calls=[json.loads(line) for line in self.log.read_text().splitlines()]
        configs=[args for args in calls if 'config' in args]
        self.assertEqual(len(configs),1)
        self.assertEqual(sum(item.endswith('/infra/openhands/hardening.yaml') for item in configs[0]),1)
        self.assertFalse(any('up' in args for args in calls))

    def test_explicit_rollback_excludes_overlay(self):
        record=self.repo/'artifacts/openhands/hardening.yaml';record.parent.mkdir(parents=True)
        record.write_text('schema_version: 1\nuid: 1000\ngid: 1000\n')
        p=self.command('rollback');self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse(record.exists())
        calls=[json.loads(line) for line in self.log.read_text().splitlines()]
        up=[args for args in calls if 'up' in args]
        self.assertEqual(len(up),1)
        self.assertFalse(any(item.endswith('/infra/openhands/hardening.yaml') for item in up[0]))


if __name__=='__main__':unittest.main()
