#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
bash "$oh_root/scripts/openhands/plan.sh"
llm_verify_model
llm_init_docker
# Never skip the backup/preflight when an older pinned container exists.
upgrade_args=(guard-up)
[[ "${llm_docker[0]}" != sudo ]] || upgrade_args+=(--sudo)
python3 "$oh_root/scripts/openhands/upgrade.py" "${upgrade_args[@]}"
mkdir -p -- "$OH_WORKSPACE/demo"
# Shared group grants the non-root image user access without recursive chown.
chmod 2770 -- "$OH_WORKSPACE" "$OH_WORKSPACE/demo"
if [[ ! -e "$OH_WORKSPACE/demo/README.md" ]]; then
    printf '# OpenHands demo\n\nSynthetic learning workspace. No secrets.\n' > "$OH_WORKSPACE/demo/README.md"
    chmod 660 -- "$OH_WORKSPACE/demo/README.md"
fi
oh_compose pull openhands openhands-proxy
# Apply the shared network to Ollama too; its existing model volume is retained.
oh_compose up -d ollama openhands openhands-proxy
# Verify project permissions as the actual image user before any agent task.
oh_compose exec --interactive=false -T openhands sh -c 'test "$(id -u)" -ne 0 && test -w /projects/demo && test -w /home/openhands/.openhands' </dev/null
bash "$oh_root/scripts/openhands/check.sh"
