#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
target="$OH_WORKSPACE/bugfix"
if [[ -e "$target" ]]; then
    printf 'Exercise already exists: %s. Refusing to overwrite agent work.\n' "$target" >&2
    exit 1
fi
mkdir -p -- "$target"
chmod 2770 -- "$target"
cp -- "$oh_root/exercises/bugfix/discounts.py" "$oh_root/exercises/bugfix/test_discounts.py" "$target/"
chmod 660 -- "$target/discounts.py" "$target/test_discounts.py"
bash "$oh_root/scripts/openhands/bugfix-baseline.sh"
