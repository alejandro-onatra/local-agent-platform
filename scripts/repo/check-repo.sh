#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$repo_root"
for path in README.md LICENSE .gitignore mise.toml mise.lock Taskfile.yml infra/host/versions.json infra/host/mise-version.json infra/llm/compose.yaml infra/llm/versions.json scripts/llm/check-inference.py infra/openhands/compose.yaml infra/openhands/versions.json docs/OPENHANDS.md docs/PLAN.md docs/OBSERVABILITY.md docs/DASHBOARDS.md infra/observability/compose.yaml infra/observability/versions.json docs/architecture/OBSERVABILITY_DIAGRAMS.md docs/EDUCATIONAL_USE.md docs/ENVIRONMENT.md scripts/host/check-gpu.sh; do
    [[ -s "$path" ]] || { printf 'Missing or empty: %s\n' "$path" >&2; exit 1; }
done
while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(find scripts -type f -name '*.sh' -print0)
printf 'Repository structure and shell syntax verified.\n'
