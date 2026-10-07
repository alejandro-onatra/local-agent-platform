#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# mise creates/activates this venv; refuse global or sudo installation.
python3 - "$repo_root" <<'PYCODE'
from pathlib import Path
import platform, sys
expected = Path(sys.argv[1]) / '.venv'
if Path(sys.prefix).resolve() != expected.resolve() or sys.prefix == sys.base_prefix:
    raise SystemExit('Use mise run env:python:setup; the project venv must be active.')
if sys.version_info[:3] != (3, 14, 4) or platform.system() != 'Linux' or platform.machine() != 'x86_64':
    raise SystemExit('This dependency lock targets Python 3.14.4 on Linux x86_64.')
PYCODE
cd -- "$repo_root"
uv sync --locked --no-dev --python "$repo_root/.venv/bin/python3"
bash "$repo_root/scripts/environment/check-python.sh"
