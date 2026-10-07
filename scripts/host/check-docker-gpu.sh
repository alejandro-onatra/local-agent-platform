#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v docker >/dev/null || { printf 'Docker is not installed.\n' >&2; exit 2; }
if docker info >/dev/null 2>&1; then
    docker_cmd=(docker)
else
    sudo -v
    docker_cmd=(sudo docker)
fi
mapfile -t images < <(python3 - "$repo_root/infra/host/versions.yaml" <<'PYCODE'
import json, sys
import yaml
images=yaml.safe_load(open(sys.argv[1]))['smoke_images']
print(images['hello-world'])
print(images['ubuntu'])
PYCODE
)
[[ "${#images[@]}" -eq 2 && "${images[0]}" == *@sha256:* && "${images[1]}" == *@sha256:* ]] || {
    printf 'Invalid smoke image lock.\n' >&2; exit 1;
}
mkdir -p -- "$repo_root/artifacts/diagnostics"
report="$(mktemp "$repo_root/artifacts/diagnostics/docker-gpu-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.txt")"
check_stack() {
    printf 'Docker/GPU check: %s\n' "$(date -u +%FT%TZ)"
    "${docker_cmd[@]}" version
    "${docker_cmd[@]}" compose version
    "${docker_cmd[@]}" buildx version
    "${docker_cmd[@]}" info --format 'Default runtime: {{.DefaultRuntime}}; available runtimes: {{range $name, $runtime := .Runtimes}}{{$name}} {{end}}'
    "${docker_cmd[@]}" run --rm --network none "${images[0]}"
    # No host files or Docker socket mounted; GPU 0 is used for a read-only driver query.
    "${docker_cmd[@]}" run --rm --network none --cap-drop ALL --security-opt no-new-privileges --gpus '"device=0"' "${images[1]}" nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    "${docker_cmd[@]}" image inspect --format '{{json .RepoDigests}}' "${images[0]}" "${images[1]}"
    printf 'RESULT: Docker, Compose, Buildx and GPU visibility passed. Inference is not yet tested.\n'
}
check_stack 2>&1 | tee "$report"
printf 'Report: %s\n' "$report"
