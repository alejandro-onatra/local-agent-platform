#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
failed=0
printf 'Checking authenticated Agent Server and Canvas API proxy.\n'
# Credentials stay inside the container; stdin carries only the probe program.
if ! oh_compose exec -T openhands python - < "$oh_root/scripts/openhands/check-backend.py"; then
    failed=1
fi
container="$(oh_compose ps --all -q openhands </dev/null)"
[[ "$container" =~ ^[a-f0-9]{12,64}$ ]] || { printf 'Cannot select one OpenHands container for diagnostics.\n' >&2; exit 1; }
printf 'Inspecting recent logs; only fixed error indicators are displayed.\n'
"${llm_docker[@]}" logs --tail 1000 "$container" 2>&1 | python3 "$oh_root/scripts/openhands/check-backend.py" --logs
exit "$failed"
