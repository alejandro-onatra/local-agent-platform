#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?Use plan, environment, check or setup}"
case "$mode" in
  plan) ;;
  setup|environment|check|invite|invite-revoke|diagnose|logs|identity-apply|models-check|models-tune) sudo -v ;;
  *) exit 2 ;;
esac
if [[ "$mode" == environment ]]; then
  exec sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/household/household.py" root-environment
fi
exec "$repo_root/.venv/bin/python3" -B "$repo_root/scripts/household/household.py" "$mode" "${@:2}"
