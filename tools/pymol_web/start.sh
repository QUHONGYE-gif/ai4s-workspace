#!/usr/bin/env bash
set -Eeuo pipefail

export DISPLAY="${DISPLAY:-:0}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export QT_X11_NO_MITSHM="${QT_X11_NO_MITSHM:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export LP_NUM_THREADS="${LP_NUM_THREADS:-1}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
NOVNC_HOST="${NOVNC_HOST:-127.0.0.1}"

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
# APT PyMOL must use Debian Python, not the workspace Python in /usr/local.
PATH="/usr/bin:/bin:$PATH" pymol "$@" &
service_pids+=("$!")

# Raw VNC is container-local. Publish noVNC only on the host loopback interface.
x11vnc -display "$DISPLAY" -localhost -rfbport "$VNC_PORT" \
    -forever -shared -nopw -noxdamage -quiet &
service_pids+=("$!")
websockify --web=/usr/share/novnc "$NOVNC_HOST:$NOVNC_PORT" "127.0.0.1:$VNC_PORT" &
service_pids+=("$!")

# Closing PyMOL or losing any service ends the container and cleans up peers.
wait -n "${service_pids[@]}"
