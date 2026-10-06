#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
obs_compose config --format json | python3 "$llm_repo_root/scripts/observability/validate-config.py"
printf 'Grafana: http://127.0.0.1:3000; internal LiteLLM: http://litellm:4000/v1\n'
printf 'Core telemetry uses native LiteLLM OTel; native agent tracing is a separate opt-in.\n'
printf 'Config prepared; host startup and ingestion checks are still required.\n'
