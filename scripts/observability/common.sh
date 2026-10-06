#!/usr/bin/env bash
# Shared helpers. Callers enable strict shell mode.
source "$(dirname -- "${BASH_SOURCE[0]}")/../openhands/common.sh"
obs_dir="$llm_repo_root/infra/observability"
obs_artifacts="$llm_repo_root/artifacts/observability"
obs_secret_dir="${XDG_DATA_HOME:-$HOME/.local/share}/agent-platform/observability"
export OBS_GRAFANA_PASSWORD="validation-only"
export OBS_LITELLM_MASTER_KEY="validation-only"
export OBS_COLLECTOR_CONFIG="$obs_dir/collector.json"
obs_args=(-f "$obs_dir/compose.yaml")
if [[ "${OBS_IGNORE_LOG_CONFIG:-0}" != 1 && -s "$obs_artifacts/logs-compose.json" ]]; then
    obs_args+=(-f "$obs_artifacts/logs-compose.json")
    export OBS_COLLECTOR_CONFIG="$obs_artifacts/collector-with-logs.json"
fi
obs_compose() {
    if [[ "${llm_docker[0]:-}" == sudo ]]; then
        sudo --preserve-env=OBS_GRAFANA_PASSWORD,OBS_LITELLM_MASTER_KEY,OBS_COLLECTOR_CONFIG docker --context default compose "${obs_args[@]}" "$@"
    else
        docker --context default compose "${obs_args[@]}" "$@"
    fi
}
obs_password() {
    [[ -f "$obs_secret_dir/admin-password" && ! -L "$obs_secret_dir/admin-password" ]] || { printf 'Missing password; run observability:up.\n' >&2; return 1; }
    export OBS_GRAFANA_PASSWORD="$(cat -- "$obs_secret_dir/admin-password")"
    [[ -f "$obs_secret_dir/litellm-master-key" && ! -L "$obs_secret_dir/litellm-master-key" ]] || { printf 'Missing LiteLLM key; run observability:up.\n' >&2; return 1; }
    export OBS_LITELLM_MASTER_KEY="$(cat -- "$obs_secret_dir/litellm-master-key")"
}

# Return 0 running, 2 starting, 1 missing/stopped; inspect only whitelisted state fields.
obs_require_running() {
    local service="$1" container state
    container="$(obs_compose ps --all -q "$service")" || return 1
    if [[ -z "$container" ]]; then
        printf 'Service %s has no container. Run task observability:up.\n' "$service" >&2
        return 1
    fi
    state="$("${llm_docker[@]}" inspect --format '{{.State.Status}}' "$container")" || return 1
    case "$state" in
        running) return 0 ;;
        created|restarting) return 2 ;;
        *)
            printf 'Service %s is not running: ' "$service" >&2
            "${llm_docker[@]}" inspect --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}' "$container" >&2
            printf 'Inspect task observability:logs; the container was created but did not stay running.\n' >&2
            return 1 ;;
    esac
}
