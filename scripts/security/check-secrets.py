#!/usr/bin/env python3
"""Scan publishable files, staged content and local history without printing secrets."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".gitleaks.toml"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def forbidden(name):
    path = Path(name)
    return (path.parts[0] in {"artifacts", "models", ".venv", ".idea", "node_modules"}
            or path.name == "mise.local.toml"
            or (path.name.startswith(".env") and path.name != ".env.example")
            or path.suffix.lower() in {".key", ".pem", ".age", ".agekey", ".p12", ".pfx", ".gguf", ".safetensors"})


def scan(tool, scratch, label, command):
    report = scratch / f"{label}.json"
    # Empty ignore file + ignore inline allowances: no hidden per-finding suppression.
    result = subprocess.run([
        tool, *command, "--config", str(CONFIG), "--redact=100", "--no-banner",
        "--no-color", "--log-level=error", "--exit-code=10",
        "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(scratch / "empty-ignore"),
        "--report-format=json", "--report-path", str(report), "--timeout=120",
    ], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=150)
    if result.returncode not in {0, 10} or not report.is_file():
        raise RuntimeError(f"{label}: scanner failed; raw output withheld to protect secrets")
    items = json.loads(report.read_text()) or []
    if bool(items) != (result.returncode == 10):
        raise RuntimeError(f"{label}: inconsistent scanner result")
    # Do not persist Match, Secret, author/email or surrounding source text.
    findings = []
    for item in items:
        name = item["File"]
        prefix = str(scratch / "candidate") + "/"
        if name.startswith(prefix):
            name = name[len(prefix):]
        findings.append({"file": name, "line": item["StartLine"],
                         "rule": item["RuleID"], "commit": item.get("Commit", "")})
    return findings


def main():
    os.umask(0o077)
    expected = tomllib.loads((ROOT / "mise.toml").read_text())["tools"]["gitleaks"]
    tool = shutil.which("gitleaks")
    if not tool:
        raise RuntimeError("Missing Gitleaks: run mise install --locked")
    version = subprocess.check_output([tool, "version"], stderr=subprocess.DEVNULL).decode().strip()
    if version != expected:
        raise RuntimeError("Gitleaks version differs from mise.toml")
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise RuntimeError("Full local history required; shallow clone detected")
    names = sorted(set(os.fsdecode(n) for n in
                       git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0") if n))
    snapshot = hashlib.sha256()
    file_count = 0
    with tempfile.TemporaryDirectory(prefix="agent-platform-secrets-") as directory:
        scratch = Path(directory)
        (scratch / "empty-ignore").touch()
        candidate = scratch / "candidate"
        candidate.mkdir()
        for name in names:
            source = ROOT / name
            if source.is_symlink():
                raise RuntimeError(f"Symlink requires explicit review: {name}")
            # Reject an unsafe index path even if its working copy was removed.
            if forbidden(name):
                raise RuntimeError(f"Unexpected publishable path: {name}")
            if not source.exists():  # Other tracked deletions still receive history/staged scans.
                continue
            if not source.is_file():
                raise RuntimeError(f"Unexpected publishable path: {name}")
            data = source.read_bytes()
            target = candidate / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            snapshot.update(os.fsencode(name) + b"\0" + hashlib.sha256(data).digest())
            file_count += 1
        # A generated fixture verifies that a real local-format key blocks publication.
        fixture = scratch / "canary"
        fixture.mkdir()
        canary = "sk-" + ("abcdef0123456789" * 4)
        (fixture / "fixture.txt").write_text("LITELLM_MASTER_KEY=" + canary)
        detected = scan(tool, scratch, "canary", ["dir", str(fixture)])
        if not any(item["rule"] == "local-litellm-master-key" for item in detected):
            raise RuntimeError("Canary detection failed")
        if canary in (scratch / "canary.json").read_text():
            raise RuntimeError("Canary report redaction failed")
        scopes = {
            "publishable_files": scan(tool, scratch, "files", ["dir", str(candidate)]),
            "staged_content": scan(tool, scratch, "staged", ["git", "--pre-commit", "--staged", str(ROOT)]),
            "local_history_all_refs": scan(tool, scratch, "history", ["git", "--log-opts=--all", str(ROOT)]),
        }
    summary = {
        "status": "failed" if any(scopes.values()) else "passed",
        "tool": f"gitleaks {version}", "binary_sha256": digest(Path(tool).read_bytes()),
        "config_sha256": digest(CONFIG.read_bytes()), "head": git("rev-parse", "HEAD").decode().strip(),
        "snapshot_sha256": snapshot.hexdigest(), "file_count": file_count,
        "canary_detection_and_redaction": "passed", "findings": scopes,
        "scope": "Git candidate files, staged content and all local refs; ignored files are excluded",
    }
    reports = ROOT / "artifacts" / "security"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", prefix="secrets-", suffix=".json", dir=reports,
                                     delete=False) as output:
        json.dump(summary, output, indent=2)
        output.write("\n")
    print(json.dumps(summary, indent=2))
    print(f"Report: {output.name}")
    return 1 if summary["status"] == "failed" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Exception text from external tools may contain sensitive data: only controlled RuntimeErrors.
        print(str(error) if isinstance(error, RuntimeError) else "Secret scan failed; incomplete analysis")
        raise SystemExit(2) from None
