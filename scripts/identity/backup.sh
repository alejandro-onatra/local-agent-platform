#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use an identity backup or rehearsal mode}"
shift
case "$mode" in
    plan|rehearsal-plan) exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/backup.py" "$mode" ;;
    key-create|key-rewrap) exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/backup.py" "$mode" --age "$(command -v age)" ;;
    create|restore-check|rehearsal-up|rehearsal-check|rehearsal-accept|rehearsal-down) ;;
    *) exit 2 ;;
esac
age_binary="$(command -v age)"
[[ "$age_binary" = /* ]] || { printf 'Run through mise exec; age is required.\n' >&2; exit 1; }
printf '[identity-backup] Authenticating in this terminal for %s.\n' "$mode"
sudo -v
printf '[identity-backup] Authentication ready. No payload or key values will be logged.\n'
report_dir="$repo_root/artifacts/security"
[[ ! -L "$repo_root/artifacts" && ! -L "$report_dir" ]] || exit 1
mkdir -p -- "$report_dir"
umask 077
report="$(mktemp "$report_dir/identity-backup-XXXXXXXX.json")"
trap 'printf "Report: %s\n" "$report"' EXIT
if [[ "$mode" == restore-check || "$mode" == rehearsal-up ]]; then
    # Keep every recovery prompt in the owner's foreground terminal. Root
    # helpers receive only ciphertext or a bounded RAM-backed archive, never a phrase.
    "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/backup.py" \
        "$mode" --age "$age_binary" "$@" | tee "$report"
    exit "${PIPESTATUS[0]}"
fi
sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin SUDO_UID="$(id -u)" \
    "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/identity/backup.py" \
    "$mode" --age "$age_binary" "$@" | tee "$report"
