#!/usr/bin/env python3
"""Resolve an official OpenHands release into the repository's pinned version lock."""
import argparse
import ast
import datetime
import difflib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "infra/openhands/versions.yaml"
LAUNCHER = ROOT / "scripts/openhands/start-agent-server.py"
CANVAS_REPO = "ghcr.io/openhands/agent-canvas"
CANVAS_SOURCE = "https://github.com/OpenHands/OpenHands.git"
SDK_SOURCE = "https://github.com/OpenHands/software-agent-sdk.git"


class UpdateError(ValueError):
    """Fixed operational error without remote command output."""


def fetch(url, *, accept="application/json"):
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": "agent-platform-version-lock"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except Exception:
        raise UpdateError("official_metadata_unavailable") from None


def git_revision(repository, tag):
    ref = f"refs/tags/{tag}"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", repository, ref, ref + "^{}"],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except Exception:
        raise UpdateError("official_source_tag_unavailable") from None
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2:
            rows[fields[1]] = fields[0]
    revision = rows.get(ref + "^{}") or rows.get(ref)
    if not revision or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise UpdateError("official_source_revision_invalid")
    return revision


def docker_prefix(config):
    """Select the default Docker Engine, retrying through sudo when needed."""
    arguments = ["--config", str(config), "--context", "default"]
    try:
        subprocess.run(
            ["docker", *arguments, "info"], check=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=30,
        )
        return ["docker", *arguments]
    except Exception:
        pass
    try:
        # Match the interactive host-terminal authentication used by other Docker tasks.
        subprocess.run(["sudo", "-v"], check=True, timeout=120)
        subprocess.run(
            ["sudo", "docker", *arguments, "info"], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return ["sudo", "docker", *arguments]
    except Exception:
        raise UpdateError("docker_engine_unavailable") from None


def image_metadata(version):
    reference = f"{CANVAS_REPO}:{version}"
    with tempfile.TemporaryDirectory(prefix="agent-platform-image-meta-") as config:
        (Path(config) / "config.json").write_text('{"auths":{}}\n')
        docker = docker_prefix(config)

        def inspect(target, raw=False):
            command = [*docker, "buildx", "imagetools", "inspect"]
            if raw:
                command.append("--raw")
            command.append(target)
            try:
                result = subprocess.run(
                    command, check=True, capture_output=True, timeout=120,
                )
            except Exception:
                raise UpdateError("pinned_registry_metadata_unavailable") from None
            return result.stdout

        summary = inspect(reference).decode("utf-8", errors="replace")
        digest_match = re.search(r"(?m)^Digest:\s+(sha256:[0-9a-f]{64})$", summary)
        if not digest_match:
            raise UpdateError("image_index_digest_invalid")
        try:
            index = json.loads(inspect(reference, raw=True))
            amd64 = [
                item for item in index["manifests"]
                if item["platform"].get("os") == "linux"
                and item["platform"].get("architecture") == "amd64"
            ]
            if len(amd64) != 1:
                raise ValueError
            child = f"{CANVAS_REPO}@{amd64[0]['digest']}"
            manifest = json.loads(inspect(child, raw=True))
            size = sum(layer["size"] for layer in manifest["layers"])
            if type(size) is not int or size <= 0:
                raise ValueError
        except Exception:
            raise UpdateError("amd64_manifest_invalid") from None
    return digest_match.group(1), size


def normalizer_hash(agent_server):
    url = (
        "https://raw.githubusercontent.com/OpenHands/software-agent-sdk/"
        f"v{agent_server}/openhands-sdk/openhands/sdk/llm/utils/telemetry.py"
    )
    source = fetch(url, accept="text/plain").decode("utf-8")
    try:
        tree = ast.parse(source)
        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "normalize_usage"
        ]
        if len(functions) != 1:
            raise ValueError
        node = functions[0]
        first = min([item.lineno for item in node.decorator_list] or [node.lineno])
        lines = source.splitlines(keepends=True)
        function_source = "".join(lines[first - 1:node.end_lineno])
    except Exception:
        raise UpdateError("usage_normalizer_source_invalid") from None
    return hashlib.sha256(function_source.encode()).hexdigest()


def release_metadata(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise UpdateError("stable_semver_required")
    tag = "v" + version
    try:
        release = json.loads(fetch(
            f"https://api.github.com/repos/OpenHands/OpenHands/releases/tags/{tag}"
        ))
        defaults = json.loads(fetch(
            f"https://raw.githubusercontent.com/OpenHands/OpenHands/{tag}/config/defaults.json",
            accept="text/plain",
        ))
        versions = defaults["versions"]
        minimum = defaults["compatibility"]["minimumAgentServer"]
        if release.get("draft") or release.get("prerelease") or release.get("tag_name") != tag:
            raise ValueError
        if versions["agentCanvas"] != version:
            raise ValueError
        agent_server = versions["agentServer"]
        automation = versions["automation"]
        if tuple(map(int, agent_server.split("."))) < tuple(map(int, minimum.split("."))):
            raise ValueError
    except Exception:
        raise UpdateError("official_release_metadata_invalid") from None
    digest, compressed_bytes = image_metadata(version)
    return {
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "version": version,
        "image": f"{CANVAS_REPO}@{digest}",
        "source_revision": git_revision(CANVAS_SOURCE, tag),
        "agent_server": agent_server,
        "agent_server_source_revision": git_revision(SDK_SOURCE, "v" + agent_server),
        "minimum_agent_server": minimum,
        "automation": automation,
        "compressed_image_bytes": compressed_bytes,
        "usage_hash": normalizer_hash(agent_server),
    }


def replace_scalar(text, key, value, after=None):
    pattern = re.compile(rf"(?m)^{re.escape(key)}:.*$")
    matches = list(pattern.finditer(text))
    line = f"{key}: {value}"
    if len(matches) == 1:
        return text[:matches[0].start()] + line + text[matches[0].end():]
    if matches:
        raise UpdateError("version_lock_key_ambiguous")
    if not after:
        raise UpdateError("version_lock_key_missing")
    anchor = re.search(rf"(?m)^{re.escape(after)}:.*$", text)
    if not anchor:
        raise UpdateError("version_lock_anchor_missing")
    end = text.find("\n", anchor.start())
    return text[:end + 1] + line + "\n" + text[end + 1:]


def lock_text(current, metadata):
    text = current
    fields = [
        ("resolved_at", f"'{metadata['resolved_at']}'", None),
        ("version", metadata["version"], None),
        ("image", metadata["image"], None),
        ("source_revision", metadata["source_revision"], None),
        ("agent_server", metadata["agent_server"], None),
        ("agent_server_source_revision", metadata["agent_server_source_revision"], "source_revision"),
        ("minimum_agent_server", metadata["minimum_agent_server"], "agent_server"),
        ("automation", metadata["automation"], None),
        ("compressed_image_bytes", str(metadata["compressed_image_bytes"]), "automation"),
    ]
    for key, value, anchor in fields:
        text = replace_scalar(text, key, value, anchor)
    return text


def launcher_text(current, metadata):
    pattern = re.compile(
        r"(?ms)^USAGE_SOURCE_SHA256_BY_VERSION = \{\n.*?^\}"
    )
    match = pattern.search(current)
    if not match:
        raise UpdateError("usage_hash_map_invalid")
    block = match.group(0)
    entries = dict(re.findall(
        r"(?m)^\s*'(\d+\.\d+\.\d+)': '([0-9a-f]{64})',$", block
    ))
    version = metadata["agent_server"]
    previous = entries.get(version)
    if previous and previous != metadata["usage_hash"]:
        raise UpdateError("usage_hash_conflicts_with_existing_pin")
    entries[version] = metadata["usage_hash"]
    rows = sorted(entries.items(), key=lambda row: tuple(map(int, row[0].split("."))))
    replacement = "USAGE_SOURCE_SHA256_BY_VERSION = {\n"
    replacement += "".join(f"    '{v}': '{h}',\n" for v, h in rows) + "}"
    return current[:match.start()] + replacement + current[match.end():]


def atomic_write(path, content):
    if path.is_symlink() or not path.is_file():
        raise UpdateError("version_source_file_unsafe")
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["plan", "apply"])
    args = parser.parse_args()
    version = os.environ.get("OPENHANDS_TARGET_VERSION", "")
    if not version:
        raise UpdateError("version_argument_required")
    metadata = release_metadata(version)
    old_lock = LOCK.read_text()
    old_launcher = LAUNCHER.read_text()
    new_lock = lock_text(old_lock, metadata)
    new_launcher = launcher_text(old_launcher, metadata)
    patches = []
    for path, old, new in [
        (LOCK, old_lock, new_lock),
        (LAUNCHER, old_launcher, new_launcher),
    ]:
        patches.extend(difflib.unified_diff(
            old.splitlines(True), new.splitlines(True),
            fromfile=str(path.relative_to(ROOT)),
            tofile=str(path.relative_to(ROOT)),
        ))
    if patches:
        sys.stdout.writelines(patches)
    else:
        print("OpenHands version lock already matches the official release.")
    if args.mode == "apply" and patches:
        # Add the compatibility guard first; an extra unused hash is harmless
        # if the following lock replacement is interrupted.
        atomic_write(LAUNCHER, new_launcher)
        atomic_write(LOCK, new_lock)
    print(json.dumps({
        "status": "planned" if args.mode == "plan" else "applied",
        "version": metadata["version"],
        "agent_server": metadata["agent_server"],
        "automation": metadata["automation"],
        "image_digest": metadata["image"].rsplit("@", 1)[1],
        "services_changed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpdateError as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        raise SystemExit(1)
