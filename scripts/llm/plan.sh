#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
python3 - "$llm_lock_file" <<'PYCODE'
import json, sys
import yaml
x=yaml.safe_load(open(sys.argv[1]))
print('Ollama version:', x['ollama']['version'])
print('Pinned image:', x['ollama']['image'])
print('Model:', x['model']['name'])
print('Expected model digest:', x['model']['digest'])
print('Model download: %.2f GB' % (x['model']['download_bytes']/1e9))
print('Context:', x['model']['context_length'])
print('API:', x['base_url'], '(localhost only; cloud features disabled)')
print('Docker context: default; named volume persists model weights outside Git/CloudDrive.')
PYCODE
# Parsing Compose does not contact the daemon or install anything.
docker --context default compose -f "$llm_compose_file" config --format json | python3 -c '
import json,sys
import yaml
from pathlib import Path
x=json.load(sys.stdin)
lock=yaml.safe_load(Path(sys.argv[1]).read_text())
s=x["services"]["ollama"]
assert s["image"]==lock["ollama"]["image"]
assert s["environment"]["OLLAMA_NO_CLOUD"]=="1"
assert int(s["environment"]["OLLAMA_CONTEXT_LENGTH"])==lock["model"]["context_length"]
assert s["ports"][0]["host_ip"]=="127.0.0.1"
assert len(x["services"])==1
print("Compose config and lock consistency verified.")
' "$llm_lock_file"
