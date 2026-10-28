#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
case "${1:?Use setup or check}" in
    setup)
        mise install --locked caddy
        bash "$repo_root/scripts/gateway/run.sh" environment
        bash "$repo_root/scripts/gateway/run.sh" cache
        ;;
    check) bash "$repo_root/scripts/gateway/run.sh" environment ;;
    *) exit 2 ;;
esac
