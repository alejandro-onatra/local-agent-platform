#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
obs_compose logs --tail 60 collector litellm prometheus tempo loki grafana blackbox
