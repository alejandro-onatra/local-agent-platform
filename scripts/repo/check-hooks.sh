#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
[[ "$(git config --local --get core.hooksPath || true)" == .githooks ]] || { printf 'Run mise run repo:hooks:install.\n' >&2; exit 1; }
[[ -f .githooks/pre-commit && ! -L .githooks/pre-commit && -x .githooks/pre-commit ]] || { printf 'Hook missing or not executable.\n' >&2; exit 1; }
bash -n .githooks/pre-commit
printf 'Local Git pre-commit hook configured: .githooks/pre-commit\n'
