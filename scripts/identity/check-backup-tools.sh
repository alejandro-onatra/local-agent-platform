#!/usr/bin/env bash
set -euo pipefail
[[ "$(age --version)" == v1.3.2 ]] || { printf 'Expected mise age 1.3.2.\n' >&2; exit 1; }
[[ "$(age-keygen --version)" == v1.3.2 ]] || exit 1
[[ -e /proc/self/fd ]] || exit 1
printf 'Pinned age/age-keygen 1.3.2 and Linux file-descriptor support verified.\n'
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
"$repo_root/.venv/bin/python3" -B - "$repo_root" <<'PYCODE'
import importlib.util
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('identity_memory_check',Path(sys.argv[1])/'scripts/identity/backup.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with module.memory_file() as handle:
    handle.write(b'synthetic');handle.seek(0)
    assert handle.read()==b'synthetic'
print('Anonymous Linux memory-backed file API verified without credentials.')
PYCODE
