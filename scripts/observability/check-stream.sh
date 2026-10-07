#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
obs_require_running litellm || exit 1
stream_container="$(obs_compose ps --all -q litellm)"
mkdir -p "$llm_repo_root/artifacts/diagnostics"
stream_report="$(mktemp "$llm_repo_root/artifacts/diagnostics/llm-stream-XXXXXX.json")"
"${llm_docker[@]}" exec -i "$stream_container" python3 - < "$llm_repo_root/scripts/observability/check-stream.py" | tee "$stream_report"
printf 'Report: %s\n' "$stream_report"
