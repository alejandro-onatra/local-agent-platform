#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/bugfix-common.sh"
bugfix_validate_files
llm_init_docker
oh_compose exec -T -w /projects/bugfix openhands python - acceptance < "$oh_root/scripts/openhands/check-bugfix.py"
