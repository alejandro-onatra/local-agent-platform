#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
# Uses Python from LiteLLM on the internal data network; publishes no backend ports.
obs_require_running litellm || exit 1
container="$(obs_compose ps --all -q litellm)"
mkdir -p "$llm_repo_root/artifacts/diagnostics"
report="$(mktemp "$llm_repo_root/artifacts/diagnostics/observability-XXXXXX.json")"
"${llm_docker[@]}" exec -i "$container" python3 - < "$llm_repo_root/scripts/observability/check-stack.py" | tee "$report"
