#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
mode="${1:-plan}"
[[ "$mode" == plan || "$mode" == apply ]] || { printf 'Use plan or apply.\n' >&2; exit 2; }
llm_init_docker
args=("$mode")
[[ "${llm_docker[0]}" != sudo ]] || args+=(--sudo)
exec python3 "$oh_root/scripts/openhands/upgrade.py" "${args[@]}"
