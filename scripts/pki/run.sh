#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use environment, plan, offline-check, online-check or create}"
shift
case "$mode" in
    environment|plan) exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/pki/pki.py" "$mode" "$@" ;;
    offline-check|online-check|create) ;;
    *) exit 2 ;;
esac
# Authentication is only for the read-only default Docker inventory. Crypto
# and all hidden phrase input remain in the owner's foreground process.
sudo -v
exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/pki/pki.py" "$mode" "$@"
