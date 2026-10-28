#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
"$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/check-source.py"
"$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/native-check.py" plan
"$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/local.py" plan
exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/backup.py" rehearsal-plan
