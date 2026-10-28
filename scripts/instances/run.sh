#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use config, plan, up, check, accept, down, diagnose, network-check, websocket-check or recovery-check}"
case "$mode" in config|plan|up|check|accept|down|diagnose|network-check|websocket-check|recovery-check) ;; *) exit 2 ;; esac
pilot_python="$repo_root/.venv/bin/python3"
[[ -x "$pilot_python" ]] || { printf 'Run mise run env:python:setup first.\n' >&2; exit 1; }
report_dir="$repo_root/artifacts/security"
[[ ! -L "$repo_root/artifacts" && ! -L "$report_dir" ]] || exit 1
mkdir -p -- "$report_dir"
umask 077
report="$(mktemp "$report_dir/instances-XXXXXXXX.json")"
if [[ "$mode" == config ]]; then
    "$pilot_python" -B "$repo_root/scripts/instances/instances.py" "$mode" | tee "$report"
else
    printf '[instances] %s: two synthetic localhost instances; current OpenHands is unchanged.\n' "$mode"
    sudo -v
    sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        "$pilot_python" -B "$repo_root/scripts/instances/instances.py" "$mode" | tee "$report"
fi
printf 'Report: %s\n' "$report"
