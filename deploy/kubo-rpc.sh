#!/bin/sh
set -eu
export LC_ALL=C

secret=${KUBO_RPC_SECRET:-}
case "$secret" in
  ''|*[!A-Za-z0-9_-]*) echo "Kubo RPC secret is missing or invalid." >&2; exit 1 ;;
esac
if [ "${#secret}" -lt 32 ] || [ "${#secret}" -gt 128 ]; then
  echo "Kubo RPC secret is missing or invalid." >&2
  exit 1
fi

# Expansion happens inside the trusted container, never in a host healthcheck argv.
exec ipfs --api=/ip4/127.0.0.1/tcp/5001 --api-auth="bearer:$secret" "$@"
