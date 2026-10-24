#!/usr/bin/env bash
set -Eeuo pipefail

service_pids=()
cleanup() {
    trap - EXIT TERM INT
    for pid in "${service_pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT

# Start the display before any program that connects to it.
Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension GLX -noreset -nolisten tcp &
display_pid=$!
service_pids+=("$display_pid")

# x11vnc and Qt must wait until the display is actually ready.
display_ready=false
for ((attempt = 0; attempt < 100; attempt++)); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        display_ready=true
        break
    fi
    if ! kill -0 "$display_pid" 2>/dev/null; then
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
service_pids+=("$!")
pymol "$@" &
service_pids+=("$!")

# Raw VNC is container-local. Publish noVNC only on the host loopback interface.
x11vnc -display "$DISPLAY" -localhost -rfbport "$VNC_PORT" \
    -forever -shared -nopw -noxdamage -quiet &
service_pids+=("$!")
websockify --web=/usr/share/novnc "0.0.0.0:$NOVNC_PORT" "127.0.0.1:$VNC_PORT" &
service_pids+=("$!")

# Closing PyMOL or losing any service ends the container and cleans up peers.
wait -n "${service_pids[@]}"
