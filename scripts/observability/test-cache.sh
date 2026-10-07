#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
llm_init_docker
cache_test_dir="$(mktemp -d)"
cache_test_container=""
cleanup() {
    if [[ -n "$cache_test_container" ]]; then
        "${llm_docker[@]}" rm "$cache_test_container" >/dev/null || true
    fi
    rm -rf -- "$cache_test_dir"
}
trap cleanup EXIT
cache_test_image="$(python3 - "$obs_dir/versions.yaml" <<'JSON'
import json,sys
import yaml
print(yaml.safe_load(open(sys.argv[1]))['components']['collector']['image'])
JSON
)"
# Extract the pinned binary from a stopped container; no network or published ports.
cache_test_container="$("${llm_docker[@]}" create --network none "$cache_test_image")"
"${llm_docker[@]}" cp "$cache_test_container:/otelcol-contrib" - | tar --extract --file - --directory "$cache_test_dir" --no-same-owner
python3 "$llm_repo_root/scripts/observability/test-cache.py" --collector "$cache_test_dir/otelcol-contrib"
