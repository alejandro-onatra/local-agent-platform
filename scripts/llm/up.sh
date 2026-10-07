#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
llm_compose up -d --wait --wait-timeout 240 ollama
python3 - "$llm_lock_file" <<'PYCODE'
import json, sys, urllib.request
import yaml
lock=yaml.safe_load(open(sys.argv[1]))
with urllib.request.urlopen(lock['base_url']+'/api/version',timeout=10) as response:
    version=json.load(response)['version']
if version!=lock['ollama']['version']:
    raise SystemExit(f"Ollama version mismatch: {version}")
print('Ollama healthy, version verified:', version)
PYCODE
