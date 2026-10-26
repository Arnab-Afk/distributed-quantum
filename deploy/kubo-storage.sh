#!/bin/sh
set -eu
export LC_ALL=C
umask 077

storage_max=${KUBO_STORAGE_MAX:-10GB}
gc_period=${KUBO_GC_PERIOD:-1h}

invalid() {
  echo 'Kubo storage settings require 1-999999 MB/GB/TB and 1-999999 s/m/h (no spaces).' >&2
  exit 1
}

positive_integer() {
  case "$1" in ''|0*|*[!0-9]*) invalid ;; esac
  [ "${#1}" -le 6 ] || invalid
}

# Restrict inputs before encoding JSON; validate everything before changing the repo.
case "$storage_max" in *MB|*GB|*TB) positive_integer "${storage_max%??}" ;; *) invalid ;; esac
case "$gc_period" in *s|*m|*h) positive_integer "${gc_period%?}" ;; *) invalid ;; esac

set_json() {
  if ! ipfs config --json "$1" "$2" >/dev/null 2>&1; then
    echo 'Kubo storage configuration failed; check the pinned release settings.' >&2
    exit 1
  fi
}

set_json Datastore.StorageMax "\"$storage_max\""
set_json Datastore.StorageGCWatermark 90
set_json Datastore.GCPeriod "\"$gc_period\""
printf '%s\n' 'Kubo storage target and automatic GC settings applied.'
