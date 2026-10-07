#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
for path in README.md LICENSE .gitignore mise.toml mise.lock Taskfile.yml pyproject.toml uv.lock infra/observability/collector.yaml infra/host/versions.yaml infra/host/mise-version.json infra/llm/compose.yaml infra/llm/versions.yaml scripts/llm/check-inference.py infra/openhands/compose.yaml infra/openhands/versions.yaml docs/openhands.md docs/plan.md docs/observability.md docs/dashboards.md infra/observability/compose.yaml infra/observability/versions.yaml docs/architecture/observability_diagrams.md docs/project_scope.md docs/environment.md scripts/host/check-gpu.sh; do
    [[ -s "$path" ]] || { printf 'Missing or empty: %s\n' "$path" >&2; exit 1; }
done
while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(find scripts -type f -name '*.sh' -print0)
printf 'Repository structure and shell syntax verified.\n'
