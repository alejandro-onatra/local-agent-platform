#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../llm/common.sh"
llm_init_docker
args=()
[[ "${llm_docker[0]}" != sudo ]] || args+=(--sudo)
exec python3 "$llm_repo_root/scripts/security/check-container.py" "${args[@]}"
