#!/bin/sh
set -eu
export LC_ALL=C
umask 077

secret=${KUBO_RPC_SECRET:-}
case "$secret" in
  ''|*[!A-Za-z0-9_-]*) echo "Kubo requires a 32-128 character base64url RPC secret." >&2; exit 1 ;;
esac
if [ "${#secret}" -lt 32 ] || [ "${#secret}" -gt 128 ]; then
  echo "Kubo requires a 32-128 character base64url RPC secret." >&2
  exit 1
fi

set_json() {
  # Native errors can include supplied values. Never print the auth configuration.
  if ! ipfs config --json "$1" "$2" >/dev/null 2>&1; then
    echo "Kubo security configuration failed; check the pinned release settings." >&2
    exit 1
  fi
}

auth=$(printf '{"backend":{"AuthSecret":"bearer:%s","AllowedPaths":["/api/v0/id","/api/v0/diag/healthy","/api/v0/add","/api/v0/cat","/api/v0/pin/add","/api/v0/pin/rm","/api/v0/pin/ls","/api/v0/dag/import","/api/v0/block/stat"]}}' "$secret")
set_json API.Authorizations "$auth"
set_json Gateway.NoFetch true
set_json Gateway.NoDNSLink true
set_json Gateway.ExposeRoutingAPI false
set_json Swarm.ConnMgr.Type '"basic"'
set_json Swarm.ConnMgr.LowWater 32
set_json Swarm.ConnMgr.HighWater 96
set_json Swarm.ResourceMgr.Enabled true
set_json Swarm.ResourceMgr.MaxFileDescriptors 1024
set_json Swarm.RelayService.Enabled false
set_json AutoNAT.ServiceMode '"disabled"'
chmod 600 "${IPFS_PATH:-/data/ipfs}/config"
printf '%s\n' 'Kubo RPC authorization and gateway/swarm controls applied.'
