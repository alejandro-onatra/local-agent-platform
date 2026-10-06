#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
# Model storage belongs to Docker, not necessarily the CloudDrive filesystem.
docker_root="$("${llm_docker[@]}" info --format '{{.DockerRootDir}}')"
python3 - "$llm_lock_file" "$docker_root" <<'PYCODE'
import json, shutil, sys
x=json.load(open(sys.argv[1]))
try:
    free=shutil.disk_usage(sys.argv[2]).free
except (PermissionError, FileNotFoundError):
    print('Docker storage free space could not be checked; review before downloading.')
else:
    required=x['model']['download_bytes']+3_000_000_000
    if free<required:
        raise SystemExit('Insufficient free space in Docker storage for model plus 3 GB margin.')
    print('Docker storage free space: %.1f GB' % (free/1e9))
print('Download size: %.2f GB' % (x['model']['download_bytes']/1e9))
PYCODE
llm_compose exec -T ollama ollama pull "$(llm_model)"
# Tags can move. Refuse inference if the downloaded manifest differs from our lock.
llm_verify_model
