#!/bin/sh
# Run as qhy on lab-gpu after installing the verified Tailscale static binaries.
# This starts an isolated userspace node; login and public routing are separate.
set -eu
test "$(id -un)" = qhy
task_root=/data1/qhy/tailscale-ai4s
test -x "$task_root/bin/tailscaled"
test -x "$task_root/bin/tailscale"
task_repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$task_root/state" "$task_root/run" "$HOME/.config/systemd/user"
chmod 700 "$task_root" "$task_root/state" "$task_root/run"
task_unit="$HOME/.config/systemd/user/ai4s-tailscale.service"
if [ -e "$task_unit" ]; then
  cmp "$task_repo/configs/ai4s-tailscale.service" "$task_unit" || {
    echo "Existing unit differs; inspect before replacing it." >&2
    exit 1
  }
else
  cp "$task_repo/configs/ai4s-tailscale.service" "$task_unit"
fi
systemctl --user daemon-reload
systemctl --user enable --now ai4s-tailscale.service
systemctl --user is-active ai4s-tailscale.service
