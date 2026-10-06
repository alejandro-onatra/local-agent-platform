#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
docker --context default compose -f "$llm_compose_file" -f "$oh_root/infra/openhands/compose.yaml" config --format json | python3 "$oh_root/scripts/openhands/validate-config.py"
printf 'OpenHands 1.24.0: localhost:8000/canvas; image download ~1.40 GB compressed.
'
printf 'Workspace: %s/demo; state in Docker volume; no Docker socket.
' "$OH_WORKSPACE"
printf 'Model profile: openai/qwen3:8b; base URL http://ollama:11434/v1; placeholder key local-only.
'
printf 'Agent container has an internal-only network. UI model setup and first conversation remain manual.
'
