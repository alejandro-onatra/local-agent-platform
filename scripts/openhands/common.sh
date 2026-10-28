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
oh_compose_args=(-f "$llm_compose_file" -f "$oh_root/infra/openhands/compose.yaml")
oh_hardening_record="$oh_root/artifacts/openhands/hardening.yaml"
if [[ -e "$oh_hardening_record" || -L "$oh_hardening_record" ]]; then
    oh_identity="$(python3 "$oh_root/scripts/openhands/hardening-settings.py" "$oh_hardening_record")" || return 1
    IFS=: read -r OH_ISOLATED_UID OH_ISOLATED_GID <<< "$oh_identity"
    export OH_ISOLATED_UID OH_ISOLATED_GID OH_ISOLATED_USER="$oh_identity"
    oh_compose_args+=(-f "$oh_root/infra/openhands/hardening.yaml")
fi
oh_compose() {
    # Preserve public Compose identity/mount inputs, never application credentials.
    if [[ "${llm_docker[0]}" == sudo ]]; then
        sudo --preserve-env=OH_HOST_GID,OH_WORKSPACE,OH_ISOLATED_UID,OH_ISOLATED_GID,OH_ISOLATED_USER docker --context default compose "${oh_compose_args[@]}" "$@"
    else
        "${llm_docker[@]}" compose "${oh_compose_args[@]}" "$@"
    fi
}
