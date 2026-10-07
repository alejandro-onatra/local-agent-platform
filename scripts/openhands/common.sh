#!/usr/bin/env bash
# Shared helpers; callers enable strict shell mode.
source "$(dirname -- "${BASH_SOURCE[0]}")/../llm/common.sh"
oh_root="$llm_repo_root"
export OH_HOST_GID="$(id -g)"
export OH_WORKSPACE="$oh_root/artifacts/openhands/projects"
oh_image() {
    python3 - "$oh_root/infra/openhands/versions.yaml" <<'PYCODE'
import json, sys
import yaml
print(yaml.safe_load(open(sys.argv[1]))['image'])
PYCODE
}
oh_compose() {
    # sudo filters exported variables; preserve only these two Compose inputs.
    if [[ "${llm_docker[0]}" == sudo ]]; then
        sudo --preserve-env=OH_HOST_GID,OH_WORKSPACE docker --context default compose \
            -f "$llm_compose_file" -f "$oh_root/infra/openhands/compose.yaml" "$@"
    else
        "${llm_docker[@]}" compose -f "$llm_compose_file" -f "$oh_root/infra/openhands/compose.yaml" "$@"
    fi
}
