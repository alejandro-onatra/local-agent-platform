#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
# Always start the core config first: recorded LogPaths may be stale after recreation.
obs_args=(-f "$obs_dir/compose.yaml")
export OBS_COLLECTOR_CONFIG="$obs_dir/collector.json"
OBS_IGNORE_LOG_CONFIG=1 bash "$llm_repo_root/scripts/observability/plan.sh"
llm_init_docker
"${llm_docker[@]}" network inspect agent-platform-local_agent-link >/dev/null || { printf 'Run task openhands:up first.\n' >&2; exit 1; }
# Credentials stay outside Git AND CloudDrive. Never print them in task output.
python3 "$llm_repo_root/scripts/observability/prepare-secrets.py" "$obs_secret_dir"
obs_password
obs_compose pull
# Validate the core configs; logs get regenerated from current container IDs below.
OBS_IGNORE_LOG_CONFIG=1 bash "$llm_repo_root/scripts/observability/validate.sh"
# Bind-mounted configuration contents are not part of the Compose service hash.
# Recreate to reload LiteLLM callbacks and Prometheus/Collector configs reliably.
obs_compose up -d --force-recreate
for attempt in {1..90}; do
    ready=1
    for service in collector litellm prometheus tempo loki grafana blackbox; do
        if obs_require_running "$service"; then
            :
        else
            state_result=$?
            [[ "$state_result" == 2 ]] || exit 1
            ready=0
        fi
    done
    # Grafana readiness alone does not prove that the model proxy is available.
    container="$(obs_compose ps --all -q litellm)"
    if [[ "$ready" == 1 ]] && curl --fail --silent http://127.0.0.1:3000/api/health >/dev/null && \
        "${llm_docker[@]}" exec "$container" python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:4000/health/liveliness", timeout=2).read()' >/dev/null 2>&1; then
        bash "$llm_repo_root/scripts/observability/configure-logs.sh"
        printf 'Grafana HTTP ready: http://127.0.0.1:3000 (user admin).\nPassword file: %s/admin-password\n' "$obs_secret_dir"
        printf 'LiteLLM profile key file: %s/litellm-master-key (copy locally; do not share).\n' "$obs_secret_dir"
        printf 'Next: task observability:check, then configure the OpenHands LLM profile.\n'
        exit 0
    fi
    sleep 2
done
printf 'Observability readiness timed out: inspect task observability:status and task observability:logs.\n' >&2
exit 1
