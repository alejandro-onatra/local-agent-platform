#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use plan or run}"
case "$mode" in plan|run) ;; *) exit 2 ;; esac
if [[ "$mode" == plan ]]; then
    exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/native-check.py" plan
fi
# Authenticate before creating the reporting pipe; never wait on hidden stdin.
sudo -v
report_dir="$repo_root/artifacts/security"
[[ ! -L "$repo_root/artifacts" && ! -L "$report_dir" ]] || exit 1
mkdir -p -- "$report_dir"
umask 077
report="$(mktemp "$report_dir/identity-native-XXXXXXXX.json")"
trap 'printf "Report: %s\n" "$report"' EXIT
sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/native-check.py" run | tee "$report"
