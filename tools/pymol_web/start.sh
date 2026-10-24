#!/usr/bin/env bash
set -Eeuo pipefail

children=()
cleanup() {
    trap - EXIT TERM INT
    for pid in "${children[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT

Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension GLX -noreset -nolisten tcp &
children+=("$!")

# x11vnc and Qt must wait until the display is actually ready.
display_ready=false
for ((attempt = 0; attempt < 100; attempt++)); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        display_ready=true
        break
    fi
    if ! kill -0 "${children[0]}" 2>/dev/null; then
        echo 'Xvfb exited before the display became ready' >&2
        exit 1
    fi
    sleep 0.1
done
if [[ "$display_ready" != true ]]; then
    echo 'Timed out waiting for the X display' >&2
    exit 1
fi

fluxbox &
children+=("$!")
pymol "$@" &
children+=("$!")

# Raw VNC is container-local. Publish noVNC only on the host loopback interface.
x11vnc -display "$DISPLAY" -localhost -rfbport "$VNC_PORT" \
    -forever -shared -nopw -noxdamage -quiet &
children+=("$!")
websockify --web=/usr/share/novnc "0.0.0.0:$NOVNC_PORT" "127.0.0.1:$VNC_PORT" &
children+=("$!")

# Closing PyMOL or losing any service ends the container and cleans up peers.
wait -n "${children[@]}"
