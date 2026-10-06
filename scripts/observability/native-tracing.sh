#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
mode="${1:-}"
[[ "$mode" == on || "$mode" == off ]] || { printf 'Usage: native-tracing.sh on|off\n' >&2; exit 2; }
llm_init_docker
files=(-f "$llm_compose_file" -f "$llm_repo_root/infra/openhands/compose.yaml")
if [[ "$mode" == on ]]; then
    "${llm_docker[@]}" network inspect agent-platform-observability_data >/dev/null
    container="$(oh_compose ps -q openhands)"
    "${llm_docker[@]}" exec "$container" /usr/local/bin/python -c 'import lmnr, opentelemetry; print("Native tracing dependency available")'
    files+=(-f "$obs_dir/openhands-tracing.yaml")
    printf 'Enabling native tracing for synthetic exercises: raw tool inputs/results may enter Collector memory before filtering.\n'
fi
if [[ "${llm_docker[0]}" == sudo ]]; then
    sudo --preserve-env=OH_HOST_GID,OH_WORKSPACE docker --context default compose "${files[@]}" up -d --no-deps openhands
else
    "${llm_docker[@]}" compose "${files[@]}" up -d --no-deps openhands
fi
printf 'OpenHands recreated; create a new conversation. Native tracing: %s.\n' "$mode"
