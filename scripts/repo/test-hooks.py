#!/usr/bin/env python3
"""Exercise actual git commits and pre-commit validation in a disposable clone."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MISE = shutil.which("mise") or str(Path.home() / ".local/bin/mise")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run(repo, args, expected=0):
    result = subprocess.run(args, cwd=repo, env=ENV, capture_output=True, text=True, timeout=240)
    if result.returncode != expected:
        # Do not expose source snippets or potential secrets when a check regresses.
        raise RuntimeError(f"Unexpected exit status for {args[0]}: {result.returncode}")
    return result


def git(repo, *args, expected=0):
    return run(repo, ["git", "-c", "user.name=Hook integration test", "-c",
                     "user.email=test@example.invalid", *args], expected)


def main():
    with tempfile.TemporaryDirectory(prefix="agent-platform-hook-test-") as directory:
        repo = Path(directory) / "repo"
        run(ROOT, ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repo)])
        # Overlay current hook changes so this test also works before their first commit.
        names = [name for name in git(ROOT, "ls-files", "--cached", "--others", "--exclude-standard").stdout.splitlines() if name]
        for name in names:
            source = ROOT / name
            target = repo / name
            if not source.exists():
                if target.is_file():
                    target.unlink()
                continue
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("Unexpected source path in hook fixture")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        run(repo, [MISE, "trust", "mise.toml"])
        run(repo, [MISE, "run", "env:python:setup"])
        git(repo, "config", "--local", "core.hooksPath", "custom-preserved")
        run(repo, [MISE, "run", "repo:hooks:install"], expected=2)
        assert git(repo, "config", "--local", "--get", "core.hooksPath").stdout.strip() == "custom-preserved"
        git(repo, "config", "--local", "--unset", "core.hooksPath")
        run(repo, [MISE, "run", "repo:hooks:install"])
        run(repo, [MISE, "run", "repo:hooks:check"])
        git(repo, "add", "--all")
        result = git(repo, "commit", "-qm", "Verified clean fixture")
        assert "Running pre-commit validation" in result.stdout + result.stderr
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        secret = "sk-" + "abcdef0123456789" * 4
        unsafe = repo / "unsafe.txt"
        unsafe.write_text("LITELLM_MASTER_KEY=" + secret)
        git(repo, "add", "unsafe.txt")
        result = git(repo, "commit", "-qm", "Rejected synthetic secret", expected=1)
        assert secret not in result.stdout + result.stderr
        assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
        git(repo, "reset", "-q", "HEAD", "--", "unsafe.txt")
        unsafe.unlink()
        script = repo / "scripts/repo/check-repo.sh"
        script.write_text(script.read_text() + "\nif\n")
        git(repo, "add", "scripts/repo/check-repo.sh")
        git(repo, "commit", "-qm", "Rejected shell syntax", expected=1)
        assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
    print(json.dumps({"status": "passed", "actual_git_commit_checks": {
        "clean_commit_accepted": True, "secret_commit_rejected_and_redacted": True,
        "invalid_shell_commit_rejected": True, "existing_hooks_path_preserved": True},
        "scope": "Disposable clone; project history is untouched"}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, OSError, subprocess.SubprocessError):
        print("Hook integration test failed; potentially sensitive command output withheld.")
        raise SystemExit(1) from None
