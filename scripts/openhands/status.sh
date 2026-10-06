#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
oh_compose ps openhands openhands-proxy
