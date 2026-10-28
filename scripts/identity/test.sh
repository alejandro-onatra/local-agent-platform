#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
exec python3 -B -m unittest discover -s tests/security -p 'test_identity*.py' -v
