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
PHASE = "initialization"


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
    global PHASE
    PHASE = "clone_and_environment"
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
        PHASE = "hook_installation"
        git(repo, "config", "--local", "core.hooksPath", "custom-preserved")
        run(repo, [MISE, "run", "repo:hooks:install"], expected=2)
        assert git(repo, "config", "--local", "--get", "core.hooksPath").stdout.strip() == "custom-preserved"
        git(repo, "config", "--local", "--unset", "core.hooksPath")
        run(repo, [MISE, "run", "repo:hooks:install"])
        run(repo, [MISE, "run", "repo:hooks:check"])
        PHASE = "clean_commit"
        # A clean, already-committed source tree still needs a real fixture change.
        (repo / "hook-check.txt").write_text("Synthetic hook integration fixture.\n")
        git(repo, "add", "--all")
        result = git(repo, "commit", "-qm", "Verified clean fixture")
        assert "Running pre-commit validation" in result.stdout + result.stderr
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        PHASE = "secret_rejection"
        secret = "sk-" + "abcdef0123456789" * 4
        unsafe = repo / "unsafe.txt"
        unsafe.write_text("LITELLM_MASTER_KEY=" + secret)
        git(repo, "add", "unsafe.txt")
        result = git(repo, "commit", "-qm", "Rejected synthetic secret", expected=1)
        assert secret not in result.stdout + result.stderr
        assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
        git(repo, "reset", "-q", "HEAD", "--", "unsafe.txt")
        unsafe.unlink()
        PHASE = "compose_rejection"
        compose = repo / "infra/openhands/compose.yaml"
        baseline = compose.read_text()
        unsafe_compose = baseline.replace("127.0.0.1:8000:8080", "0.0.0.0:8000:8080")
        assert unsafe_compose != baseline
        compose.write_text(unsafe_compose)
        git(repo, "add", "infra/openhands/compose.yaml")
        git(repo, "commit", "-qm", "Rejected unintended network exposure", expected=1)
        assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
        compose.write_text(baseline)
        git(repo, "reset", "-q", "HEAD", "--", "infra/openhands/compose.yaml")
        PHASE = "shell_rejection"
        script = repo / "scripts/repo/check-repo.sh"
        script.write_text(script.read_text() + "\nif\n")
        git(repo, "add", "scripts/repo/check-repo.sh")
        git(repo, "commit", "-qm", "Rejected shell syntax", expected=1)
        assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
    print(json.dumps({"status": "passed", "actual_git_commit_checks": {
        "clean_commit_accepted": True, "secret_commit_rejected_and_redacted": True,
        "unsafe_compose_commit_rejected": True, "invalid_shell_commit_rejected": True, "existing_hooks_path_preserved": True},
        "scope": "Disposable clone; project history is untouched"}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, OSError, subprocess.SubprocessError):
        print(json.dumps({"status":"failed","phase":PHASE,"details":"Potentially sensitive command output withheld"}))
        raise SystemExit(1) from None
