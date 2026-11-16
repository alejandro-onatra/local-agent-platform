import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/openhands/update-versions.py"
SPEC = importlib.util.spec_from_file_location("openhands_update_versions", MODULE_PATH)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class DockerSelectionTests(unittest.TestCase):
    def test_uses_default_engine_without_sudo_when_available(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.object(updater.subprocess, "run") as run:
                run.return_value = subprocess.CompletedProcess([], 0)
                prefix = updater.docker_prefix(config)

        self.assertEqual(prefix[:1], ["docker"])
        self.assertIn("--context", prefix)
        run.assert_called_once()

    def test_retries_default_engine_with_sudo_after_unprivileged_failure(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.object(updater.subprocess, "run") as run:
                run.side_effect = [
                    subprocess.CalledProcessError(1, ["docker"]),
                    subprocess.CompletedProcess([], 0),
                    subprocess.CompletedProcess([], 0),
                ]
                prefix = updater.docker_prefix(config)

        self.assertEqual(prefix[:2], ["sudo", "docker"])
        self.assertIn("--config", prefix)
        self.assertIn("--context", prefix)
        self.assertEqual(run.call_args_list[1].args[0], ["sudo", "-v"])


class ComposeImageWiringTests(unittest.TestCase):
    def test_every_compose_entrypoint_receives_the_locked_image(self):
        compose = (ROOT / "infra/openhands/compose.yaml").read_text()
        common = (ROOT / "scripts/openhands/common.sh").read_text()
        upgrade = (ROOT / "scripts/openhands/upgrade.py").read_text()
        plan = (ROOT / "scripts/openhands/plan.sh").read_text()
        tracing = (ROOT / "scripts/observability/native-tracing.sh").read_text()

        self.assertIn("image: ${OH_IMAGE:?Run task openhands:up}", compose)
        self.assertIn('export OH_IMAGE="$(oh_image)"', common)
        self.assertIn("OH_IMAGE", upgrade)
        self.assertIn("llm_init_docker", plan)
        self.assertIn("oh_compose config --format json", plan)
        self.assertIn("OH_IMAGE", tracing)


if __name__ == "__main__":
    unittest.main()
