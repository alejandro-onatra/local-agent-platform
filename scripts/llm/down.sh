#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
# Keep named volumes/model weights. No --volumes and no Docker-wide cleanup.
llm_compose down
