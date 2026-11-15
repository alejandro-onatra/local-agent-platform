#!/usr/bin/env bash
set -euo pipefail

umask 077
docker_config_dir="$(mktemp -d "${TMPDIR:-/tmp}/agent-platform-trivy.XXXXXX")"
trap 'rm -rf -- "$docker_config_dir"' EXIT

printf '{"auths":{}}\n' > "$docker_config_dir/config.json"

DOCKER_CONFIG="$docker_config_dir" trivy fs \
  --scanners vuln,misconfig \
  --severity HIGH,CRITICAL \
  --exit-code 1 .
