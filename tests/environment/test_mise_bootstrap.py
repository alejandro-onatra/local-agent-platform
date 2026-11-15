"""Exercise the pinned mise bootstrap against a synthetic local HTTP server."""
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        server = self.server
        server.request_count += 1
        if server.request_count <= len(server.failure_statuses):
            status = server.failure_statuses[server.request_count - 1]
            payload = b"synthetic temporary failure"
        else:
            status = 200
            payload = server.archive_payload
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


@unittest.skipUnless(
    platform.system() == "Linux"
    and platform.machine().lower() in {"x86_64", "amd64"}
    and os.geteuid() != 0,
    "The pinned bootstrap supports non-root Linux x86_64 only.",
)
class MiseBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mise-bootstrap-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.home = Path(self.temp.name) / "home"
        self.installer = self.root / "scripts/bootstrap/install-mise.sh"
        self.lock_path = self.root / "infra/host/mise-version.json"
        self.installer.parent.mkdir(parents=True)
        self.lock_path.parent.mkdir(parents=True)
        self.home.mkdir()
        shutil.copyfile(ROOT / "scripts/bootstrap/install-mise.sh", self.installer)

        self.binary = b"synthetic mise fixture; never executed"
        self.archive = self.make_archive(self.binary)
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), FixtureHandler
        )
        self.server.failure_statuses = []
        self.server.request_count = 0
        self.server.archive_payload = self.archive
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.stop_server)

        url = f"http://127.0.0.1:{self.server.server_port}/mise.tar.gz"
        lock = {
            "version": "test-fixture",
            "url": url,
            "sha256": hashlib.sha256(self.archive).hexdigest(),
            "binary_sha256": hashlib.sha256(self.binary).hexdigest(),
        }
        self.lock_path.write_text(json.dumps(lock), encoding="utf-8")
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        for name in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
        ):
            self.env.pop(name, None)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    @staticmethod
    def make_archive(binary):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            member = tarfile.TarInfo("mise-test/bin/mise")
            member.mode = 0o755
            member.size = len(binary)
            archive.addfile(member, io.BytesIO(binary))
        return output.getvalue()

    def run_installer(self):
        return subprocess.run(
            ["bash", str(self.installer)],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def installed_binary(self):
        return self.home / ".local/bin/mise"

    def test_transient_server_errors_retry_then_install_verified_binary(self):
        self.server.failure_statuses = [503, 504]

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, "Bootstrap should recover after retries.")
        self.assertEqual(self.server.request_count, 3)
        self.assertEqual(self.installed_binary().read_bytes(), self.binary)
        self.assertEqual(self.installed_binary().stat().st_mode & 0o777, 0o755)

    def test_permanent_not_found_is_not_retried_or_installed(self):
        self.server.failure_statuses = [404]

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.server.request_count, 1)
        self.assertFalse(self.installed_binary().exists())

    def test_checksum_mismatch_fails_closed_without_retry_or_install(self):
        self.server.archive_payload = b"tampered synthetic download"

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.server.request_count, 1)
        self.assertFalse(self.installed_binary().exists())
        self.assertIn("Download checksum mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
