#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
[[ "$(git rev-parse --show-toplevel)" == "$repo_root" ]] || { printf 'Unexpected Git root.\n' >&2; exit 2; }
existing="$(git config --get core.hooksPath || true)"
if [[ -n "$existing" && "$existing" != .githooks ]]; then
    printf 'Existing core.hooksPath differs; refusing to replace it: %s\n' "$existing" >&2
    exit 2
fi
[[ -f .githooks/pre-commit && ! -L .githooks/pre-commit ]] || { printf 'Missing regular hook file.\n' >&2; exit 2; }
bash -n .githooks/pre-commit
chmod 0755 .githooks/pre-commit
git config --local core.hooksPath .githooks
bash scripts/repo/check-hooks.sh
