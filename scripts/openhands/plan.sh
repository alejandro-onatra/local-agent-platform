#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
docker --context default compose "${oh_compose_args[@]}" config --format json | python3 "$oh_root/scripts/openhands/validate-config.py"
python3 - "$oh_root/infra/openhands/versions.yaml" <<'PYCODE'
import sys,yaml
lock=yaml.safe_load(open(sys.argv[1]))
print(f"OpenHands {lock['version']}: localhost:8000/canvas; image download ~{lock['compressed_image_bytes']/1e9:.2f} GB compressed.")
PYCODE
printf 'Workspace: %s/demo; state in Docker volume; no Docker socket.
' "$OH_WORKSPACE"
printf 'Model profile: openai/qwen3:8b; base URL http://ollama:11434/v1; placeholder key local-only.
'
printf 'Agent container has an internal-only network. UI model setup and first conversation remain manual.
'
