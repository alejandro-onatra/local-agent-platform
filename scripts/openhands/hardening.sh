#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
mode="${1:-plan}"
[[ "$mode" == plan || "$mode" == apply || "$mode" == rollback ]] || { printf 'Use plan, apply or rollback.\n' >&2; exit 1; }
record="$oh_root/artifacts/openhands/hardening.yaml"
[[ ! -L "$record" && ! -L "$(dirname -- "$record")" ]] || { printf 'Linked activation location rejected.\n' >&2; exit 1; }
printf '[security] Connecting to Docker; sudo may authenticate in this terminal.\n'
llm_init_docker
printf '[security] Docker connection ready.\n'
if [[ "$mode" == rollback ]]; then
    [[ -f "$record" ]] || { printf 'No active hardening record.\n'; exit 0; }
    saved="$(mktemp)"
    chmod 600 "$saved"
    cp -- "$record" "$saved"
    rm -- "$record"
    source "$oh_root/scripts/openhands/common.sh"
    if oh_compose up -d --no-deps --force-recreate openhands openhands-proxy; then
        rm -- "$saved"
        printf 'Restored previous image-user/writable-root profile; state and workspace retained.\n'
    else
        cp -- "$saved" "$record"
        rm -- "$saved"
        printf 'Rollback failed; activation record restored. Inspect service status locally.\n' >&2
        exit 1
    fi
    exit 0
fi
printf '[security] Locating the existing OpenHands container.\n'
container="$(oh_compose ps --all -q openhands </dev/null)"
[[ -n "$container" ]] || { printf 'OpenHands was not found in agent-platform-local. Inspect task openhands:status.\n' >&2; exit 1; }
[[ "$container" != *$'\n'* ]] || { printf 'Multiple OpenHands containers found; inspect task openhands:status.\n' >&2; exit 1; }
running="$("${llm_docker[@]}" inspect --format '{{.State.Running}}' "$container")"
[[ "$running" == true ]] || { printf 'OpenHands exists but is not running. Inspect task openhands:status before starting it.\n' >&2; exit 1; }
image_id="$("${llm_docker[@]}" inspect --format '{{.Image}}' "$container")"
"${llm_docker[@]}" image inspect --format '{{json .RepoDigests}}' "$image_id" | python3 -c 'import json,sys; expected=sys.argv[1]; raise SystemExit(0 if expected in json.load(sys.stdin) else 1)' "$(oh_image)"
printf '[security] Checking the container identity without interactive input.\n'
identity="$(oh_compose exec --interactive=false -T openhands python -c 'import os; print(f"{os.getuid()}:{os.getgid()}")' </dev/null)"
[[ "$identity" =~ ^([1-9][0-9]{0,8}):([1-9][0-9]{0,8})$ ]] || { printf 'Cannot apply hardening with an unverified/non-root identity.\n' >&2; exit 1; }
export OH_ISOLATED_UID="${BASH_REMATCH[1]}" OH_ISOLATED_GID="${BASH_REMATCH[2]}" OH_ISOLATED_USER="$identity"
[[ -f "$record" ]] || oh_compose_args+=(-f "$oh_root/infra/openhands/hardening.yaml")
# Config is public; discard its normalized output rather than printing raw fields.
printf '[security] Verifying the installed Python backend before selecting its launcher.\n'
# Stdin carries the read-only probe; it does not launch a second server.
oh_compose exec -T openhands python - --runtime-check < "$oh_root/scripts/openhands/start-agent-server.py"
printf '[security] Validating the hardening Compose configuration.\n'
oh_compose config --quiet </dev/null
printf 'Prepared profile: verified UID:GID %s, readonly root, enforcing Docker AppArmor profile and bounded temporary filesystems.\n' "$identity"
printf 'Persistent workspace/state quotas, tenant isolation and egress acceptance remain pending.\n'
[[ "$mode" == apply ]] || exit 0
# Apply is an explicit operational command: it recreates OpenHands/proxy, not Ollama.
printf 'Recreating OpenHands/proxy. Run only after stopping active agent work; persistent data is retained.\n'
mkdir -p -- "$(dirname -- "$record")"
saved="$(mktemp)"
chmod 600 "$saved"
had_record=0
if [[ -f "$record" ]]; then cp -- "$record" "$saved"; had_record=1; fi
python3 - "$record" "$OH_ISOLATED_UID" "$OH_ISOLATED_GID" <<'PY'
import os,sys,tempfile
from pathlib import Path
os.umask(0o077)
target=Path(sys.argv[1])
with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,delete=False) as stream:
    stream.write(f'schema_version: 1\nuid: {int(sys.argv[2])}\ngid: {int(sys.argv[3])}\n')
os.replace(stream.name,target)
PY
if oh_compose up -d --no-deps --force-recreate openhands openhands-proxy && { printf '[security] Waiting for UI, authenticated backend/proxy and model connectivity checks.\n'; bash "$oh_root/scripts/openhands/check.sh"; }; then
    rm -- "$saved"
    printf 'Profile recreated and UI/backend/model checks passed. Run task security:container:check for effective restrictions.\n'
else
    if [[ "$had_record" == 1 ]]; then cp -- "$saved" "$record"; else rm -- "$record"; fi
    rm -- "$saved"
    # Reload only public activation metadata; no application state is deleted.
    source "$oh_root/scripts/openhands/common.sh"
    oh_compose up -d --no-deps --force-recreate openhands openhands-proxy || true
    printf 'Candidate failed health/compatibility checks; prior activation record restored. Compose/launcher file revisions are not reverted. Inspect status.\n' >&2
    exit 1
fi
