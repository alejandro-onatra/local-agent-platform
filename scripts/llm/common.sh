#!/usr/bin/env bash
# Shared functions; callers must enable set -euo pipefail.
llm_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
llm_compose_file="$llm_repo_root/infra/llm/compose.yaml"
llm_lock_file="$llm_repo_root/infra/llm/versions.json"

llm_init_docker() {
    command -v docker >/dev/null || { printf 'Docker is not installed.\n' >&2; return 2; }
    # Explicit Linux Engine context avoids stale Docker Desktop/DOCKER_HOST settings.
    if docker --context default info >/dev/null 2>&1; then
        llm_docker=(docker --context default)
    else
        printf 'Docker Engine requires sudo. Run this task in the host terminal.\n'
        sudo -v || return "$?"
        llm_docker=(sudo docker --context default)
        "${llm_docker[@]}" info >/dev/null
    fi
}

llm_compose() {
    "${llm_docker[@]}" compose -f "$llm_compose_file" "$@"
}

llm_model() {
    python3 - "$llm_lock_file" <<'PYCODE'
import json, sys
print(json.load(open(sys.argv[1]))['model']['name'])
PYCODE
}

llm_verify_model() {
    python3 "$llm_repo_root/scripts/llm/check-inference.py" --model-only
}
