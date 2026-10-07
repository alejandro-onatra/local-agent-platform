#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
# --check validates the existing environment; it does not install or edit the lock.
uv sync --locked --check --no-dev --python "$repo_root/.venv/bin/python3"
python3 - "$repo_root" <<'PYCODE'
from pathlib import Path
import sys
try:
    import yaml
except ImportError:
    raise SystemExit('Missing PyYAML: run mise run env:python:setup.') from None
expected = Path(sys.argv[1])/'.venv'
if sys.version_info[:3] != (3, 14, 4) or yaml.__version__ != '6.0.3' or Path(sys.prefix).resolve() != expected.resolve():
    raise SystemExit('Use mise install --locked and mise run env:python:setup.')
print('Project Python 3.14.4, uv lock synchronization and PyYAML 6.0.3 verified.')
PYCODE
