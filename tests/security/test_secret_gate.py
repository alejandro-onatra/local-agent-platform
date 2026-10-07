"""Run the real secret gate against disposable Git repositories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SecretGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="secret-gate-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        for name in ("mise.toml", ".gitleaks.toml", "scripts/security/check-secrets.py"):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.git("init", "-q")
        (self.repo / ".gitignore").write_text(".env\nartifacts/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Clean baseline")
        self.canary = "sk-" + "0123456789abcdef" * 4

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=Security test", "-c",
                        "user.email=test@example.invalid", *args], cwd=self.repo,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def run_gate(self, expected_code):
        result = subprocess.run([sys.executable, "scripts/security/check-secrets.py"],
                                cwd=self.repo, text=True, capture_output=True, timeout=180)
        # Never include captured output in failed assertions: could expose a regression.
        self.assertNotIn(self.canary, result.stdout + result.stderr, "Canary exposed")
        self.assertEqual(result.returncode, expected_code, "Unexpected gate exit status")
        if expected_code == 2:
            return None
        return json.loads(result.stdout.split("\nReport:")[0])

    def test_clean_repo_with_ignored_runtime_secret_passes(self):
        (self.repo / ".env").write_text("LITELLM_MASTER_KEY=" + self.canary)
        report = self.run_gate(0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["canary_detection_and_redaction"], "passed")

    def test_untracked_secret_blocks(self):
        (self.repo / "unsafe.txt").write_text("LITELLM_MASTER_KEY=" + self.canary)
        report = self.run_gate(1)
        self.assertTrue(report["findings"]["publishable_files"])

    def test_staged_secret_blocks_even_when_working_copy_clean(self):
        target = self.repo / "unsafe.txt"
        target.write_text("LITELLM_MASTER_KEY=" + self.canary)
        self.git("add", "unsafe.txt")
        target.write_text("Clean working copy\n")
        report = self.run_gate(1)
        self.assertFalse(report["findings"]["publishable_files"])
        self.assertTrue(report["findings"]["staged_content"])

    def test_deleted_historical_secret_blocks(self):
        target = self.repo / "unsafe.txt"
        target.write_text("LITELLM_MASTER_KEY=" + self.canary)
        self.git("add", "unsafe.txt")
        self.git("commit", "-qm", "Synthetic historical fixture")
        target.unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "Delete historical fixture")
        report = self.run_gate(1)
        self.assertFalse(report["findings"]["publishable_files"])
        self.assertFalse(report["findings"]["staged_content"])
        self.assertTrue(report["findings"]["local_history_all_refs"])

    def test_symlink_fails_closed(self):
        (self.repo / "external-link").symlink_to(ROOT / "README.md")
        self.run_gate(2)


if __name__ == "__main__":
    unittest.main()
