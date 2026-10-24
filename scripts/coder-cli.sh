#!/bin/sh
# Use this project's CLI and configuration without changing system-wide settings.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CLI="$ROOT/.local/tools/coder/coder"
if [ ! -x "$CLI" ]; then
    echo 'Coder CLI is not installed for this checkout; see docs/environment.md.' >&2
    exit 1
fi
exec "$CLI" --global-config "$ROOT/.local/tools/coder/config" "$@"
