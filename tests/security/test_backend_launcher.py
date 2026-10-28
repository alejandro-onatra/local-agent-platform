"""Verify locked module requirements and upstream argument forwarding."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('backend_launcher',ROOT/'scripts/openhands/start-agent-server.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class BackendLauncherTests(unittest.TestCase):
    def test_wrong_version_or_missing_module_is_rejected(self):
        for version,found in [('1.49.5',object()),('1.53.0',None)]:
            with patch.object(module.importlib.metadata,'version',return_value=version), patch.object(module.importlib.util,'find_spec',return_value=found):
                self.assertFalse(module.runtime_ready())

    def test_runtime_probe_does_not_launch_server(self):
        with patch.object(module,'runtime_ready',return_value=True),patch.object(module,'verify_usage_compatibility'),patch.object(module.sys,'argv',['launcher','--runtime-check']),patch.object(module.runpy,'run_module') as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(),0);run.assert_not_called()

    def test_missing_runtime_fails_closed_without_traceback(self):
        out=io.StringIO()
        with patch.object(module,'runtime_ready',return_value=False),patch.object(module.runpy,'run_module') as run,contextlib.redirect_stderr(out):
            self.assertEqual(module.main(),1);run.assert_not_called()
        self.assertIn('unavailable',out.getvalue())

    def test_import_failure_is_safe_and_does_not_fall_back_to_frozen_binary(self):
        with patch.object(module.importlib.metadata,'version',side_effect=ImportError('sensitive detail')):
            self.assertFalse(module.runtime_ready())

    def test_launch_preserves_entrypoint_arguments(self):
        args=['launcher','--port','18000','--import-modules','canvas_ui_tool']
        with patch.object(module,'runtime_ready',return_value=True),patch.object(module,'verify_usage_compatibility'),patch.object(module.sys,'argv',args),patch.object(module.runpy,'run_module') as run:
            self.assertEqual(module.main(),0)
            run.assert_called_once_with('openhands.agent_server',run_name='__main__',alter_sys=True)
            self.assertEqual(module.sys.argv,args)


if __name__=='__main__':unittest.main()
