#!/usr/bin/env bash
# Shared helpers; callers enable strict mode.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
bugfix_validate_files() {
    for filename in discounts.py test_discounts.py; do
        [[ -f "$OH_WORKSPACE/bugfix/$filename" && ! -L "$OH_WORKSPACE/bugfix/$filename" ]] || {
            printf 'Missing regular exercise file: %s. Run openhands:bugfix:prepare.\n' "$filename" >&2
            return 1
        }
    done
    cmp -s -- "$oh_root/exercises/bugfix/test_discounts.py" "$OH_WORKSPACE/bugfix/test_discounts.py" || {
        printf 'Exercise tests changed: acceptance requires original tests.\n' >&2
        return 1
    }
}
