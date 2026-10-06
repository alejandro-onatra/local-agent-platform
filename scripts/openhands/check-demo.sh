#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
for filename in sum.py test_sum.py; do
    [[ -f "$OH_WORKSPACE/demo/$filename" ]] || {
        printf 'Missing demo file: %s. Complete the OpenHands conversation first.\n' "$filename" >&2
        exit 1
    }
done
llm_init_docker
# Execute generated code inside the existing non-root agent container, not on host.
oh_compose exec -T -w /projects/demo openhands python - < "$oh_root/scripts/openhands/check-demo.py"
