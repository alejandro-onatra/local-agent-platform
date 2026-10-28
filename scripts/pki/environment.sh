#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
case "${1:?Use setup or check}" in
    setup) mise install --locked aqua:smallstep/cli ;;
    check) ;;
    *) exit 2 ;;
esac
exec bash "$repo_root/scripts/pki/run.sh" environment
