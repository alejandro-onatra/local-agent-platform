#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
mkdir -p "$obs_artifacts"
# Inspect only named laboratory services, never all host containers.
for service in openhands ollama; do
    id="$(oh_compose ps -q "$service")"
    [[ -n "$id" ]] || { printf 'Service missing: %s\n' "$service" >&2; exit 1; }
    "${llm_docker[@]}" inspect --format '{"Id":{{json .Id}},"LogPath":{{json .LogPath}},"Driver":{{json .HostConfig.LogConfig.Type}}}'  "$id" > "$obs_artifacts/inspect-$service.json"
done
obs_require_running litellm || exit 1
id="$(obs_compose ps --all -q litellm)"
"${llm_docker[@]}" inspect --format '{"Id":{{json .Id}},"LogPath":{{json .LogPath}},"Driver":{{json .HostConfig.LogConfig.Type}}}'  "$id" > "$obs_artifacts/inspect-litellm.json"
# Only Id, LogPath and logging driver are inspected; no environment or secrets.
python3 "$llm_repo_root/scripts/observability/configure-logs.py"
rm -- "$obs_artifacts/inspect-openhands.json" "$obs_artifacts/inspect-ollama.json" "$obs_artifacts/inspect-litellm.json"
# Reload the generated override, and preserve its absolute Collector config path.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
obs_password
obs_compose up -d --no-deps collector
printf 'Collector tails three selected container log directories, read-only.\nRe-run after those containers are recreated.\n'
