#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
python3 "$llm_repo_root/scripts/llm/check-inference.py"
