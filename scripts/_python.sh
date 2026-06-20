#!/usr/bin/env bash

set -e

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$@"
fi

if command -v py >/dev/null 2>&1; then
  exec py -3.14 "$@"
fi

echo "error: python3 or py -3.14 required" >&2
exit 1
