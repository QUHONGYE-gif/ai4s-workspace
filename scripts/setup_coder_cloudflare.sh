#!/bin/sh
# Run as qhy on lab-gpu. Preparation does not start or publish a tunnel.
set -eu
task_mode=${1:---prepare}
case "$task_mode" in
  --prepare|--start) ;;
  *) echo "Usage: $0 [--prepare|--start]" >&2; exit 2 ;;
esac
test "$(id -un)" = qhy
test "$(id -u)" = 1029
task_root=/data1/qhy/cloudflared-ai4s
task_repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test -x "$task_root/bin/cloudflared"
umask 077
mkdir -p "$task_root/logs" "$HOME/.config/systemd/user"
chmod 700 "$task_root" "$task_root/logs"
task_unit="$HOME/.config/systemd/user/ai4s-cloudflared.service"
if [ -e "$task_unit" ]; then
  cmp "$task_repo/configs/ai4s-cloudflared.service" "$task_unit" || {
    echo "Existing unit differs; inspect before replacing it." >&2
    exit 1
  }
else
  cp "$task_repo/configs/ai4s-cloudflared.service" "$task_unit"
fi
systemctl --user daemon-reload
if [ "$task_mode" = --prepare ]; then
  echo "Unit prepared. No service start or Coder URL change requested."
  exit 0
fi
test -s "$task_root/tunnel-token" || {
  echo "Save the tunnel token to $task_root/tunnel-token first." >&2
  exit 1
}
test "$(stat -c %u "$task_root/tunnel-token")" = "$(id -u)"
test ! -L "$task_root/tunnel-token"
chmod 600 "$task_root/tunnel-token"
systemctl --user enable --now ai4s-cloudflared.service
systemctl --user is-active ai4s-cloudflared.service
echo "Process active; verify Cloudflare connection logs and public Coder access separately."
