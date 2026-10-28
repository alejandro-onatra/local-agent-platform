#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use source, environment, plan, cache, issue, up, check or down}"
case "$mode" in
    source|environment|plan|issue|refresh) ;;
    cache|up|check|down) sudo -v ;;
    *) exit 2 ;;
esac
exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/gateway/gateway.py" "$mode"
