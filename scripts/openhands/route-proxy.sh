#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
: "${OH_CONVERSATION_ID:?Set CONVERSATION_ID in task openhands:route:proxy}"
[[ "$OH_CONVERSATION_ID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || { printf 'Invalid conversation UUID\n' >&2; exit 2; }
llm_init_docker
oh_compose exec -T openhands python - "$OH_CONVERSATION_ID" --profile "${OH_LLM_PROFILE:-local-qwen3-8b}" < "$oh_root/scripts/openhands/route-proxy.py"
