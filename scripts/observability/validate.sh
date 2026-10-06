#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
obs_compose run --rm --no-deps collector validate --config=/etc/otel/config.yaml
obs_compose run --rm --no-deps --entrypoint /bin/promtool prometheus check config /etc/prometheus/prometheus.yaml
obs_compose run --rm --no-deps loki -config.file=/etc/loki/config.yaml -verify-config=true
obs_compose run --rm --no-deps tempo --config.file=/etc/tempo/config.yaml --config.verify=true
obs_compose run --rm --no-deps --entrypoint /bin/promtool prometheus check rules /etc/prometheus/alerts.yaml
obs_compose run --rm --no-deps blackbox --config.file=/etc/blackbox/config.yaml --config.check
obs_compose run --rm --no-deps -v "$llm_repo_root/tests/observability:/tests/observability:ro" -v "$obs_dir:/infra/observability:ro" --entrypoint /bin/promtool prometheus test rules /tests/observability/alerts.test.yaml
printf 'Native configuration validation passed.\n'
