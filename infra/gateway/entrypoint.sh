#!/bin/sh
set -euC
umask 077
# The pinned official image grants file capabilities to /usr/bin/caddy. Execute
# the identical bytes without that xattr, keeping the capability bounding set empty.
source=/usr/bin/caddy
binary=/run/caddy-bin/caddy
cat "$source" > "$binary"
source_hash="$(sha256sum "$source")"
binary_hash="$(sha256sum "$binary")"
[ "${source_hash%% *}" = "${binary_hash%% *}" ] || exit 1
chmod 0500 "$binary"
exec "$binary" "$@"
