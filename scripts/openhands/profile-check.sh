#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
# Read-only API inspection. Credentials stay inside the agent container.
oh_compose exec -T openhands python - < "$oh_root/scripts/openhands/profile-check.py"
