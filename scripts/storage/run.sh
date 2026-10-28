#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use plan, setup, check, accept or unmount}"
case "$mode" in plan|setup|check|accept|unmount) ;; *) exit 2 ;; esac
storage_python="$repo_root/.venv/bin/python3"
[[ -x "$storage_python" ]] || { printf 'Run mise run env:python:setup first.\n' >&2; exit 1; }
# Only synthetic report fields are emitted. No raw mount/Docker output is displayed.
report_dir="$repo_root/artifacts/security"
[[ ! -L "$repo_root/artifacts" && ! -L "$report_dir" ]] || exit 1
mkdir -p -- "$report_dir"
umask 077
report="$(mktemp "$report_dir/storage-XXXXXXXX.json")"
if [[ "$mode" == plan ]]; then
    "$storage_python" -B "$repo_root/scripts/storage/storage.py" "$mode" | tee "$report"
else
    printf '[storage] %s: fixed synthetic pilot only; existing services/data are unchanged.\n' "$mode"
    sudo -v
    # Avoid preserving user-controlled environment in privileged mount operations.
    sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        "$storage_python" -B "$repo_root/scripts/storage/storage.py" "$mode" | tee "$report"
fi
printf 'Report: %s\n' "$report"
