#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
obs_require_running litellm || exit 1
cache_check_container="$(obs_compose ps --all -q litellm)"
mkdir -p "$llm_repo_root/artifacts/diagnostics"
cache_check_report="$(mktemp "$llm_repo_root/artifacts/diagnostics/llm-cache-XXXXXX.json")"
"${llm_docker[@]}" exec -i "$cache_check_container" python3 - < "$llm_repo_root/scripts/observability/check-cache.py" | tee "$cache_check_report"
printf 'Report: %s\n' "$cache_check_report"
