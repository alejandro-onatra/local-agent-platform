#!/usr/bin/env bash
set -euo pipefail
# The native entrypoint generates per-instance session/encryption keys in state.
umask 077
exec /opt/agent-canvas/entrypoint.sh
