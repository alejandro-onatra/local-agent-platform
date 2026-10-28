#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
python3 "$oh_root/scripts/openhands/check-ui.py"
llm_init_docker
printf 'Checking authenticated Agent Server and Canvas API proxy.\n'
# This program is supplied via stdin; keep stdin attached but do not allocate a TTY.
oh_compose exec -T openhands python - < "$oh_root/scripts/openhands/check-backend.py"
# Test the real DNS/network path from Agent Server to the existing Ollama.
oh_compose exec --interactive=false -T openhands python -c 'import json, urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); d=json.load(o.open("http://ollama:11434/api/tags",timeout=10)); assert any(m["name"]=="qwen3:8b" and m["digest"].removeprefix("sha256:")=="500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41" for m in d["models"]); print("Container-to-Ollama DNS/API and model digest verified.")' </dev/null
printf 'RESULT: UI, authenticated backend/proxy and internal LLM connection passed; agent conversation remains pending.
'
