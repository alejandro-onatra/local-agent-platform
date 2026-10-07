#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# Sequential environment steps; fail immediately before moving to the next layer.
bash "$repo_root/scripts/environment/setup-python.sh"
bash "$repo_root/scripts/repo/check-repo.sh"
bash "$repo_root/scripts/host/check-gpu.sh"
bash "$repo_root/scripts/host/install-docker-gpu.sh" --apply
