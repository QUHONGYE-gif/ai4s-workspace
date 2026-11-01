#!/usr/bin/env bash
# Run inside the existing workspace; Coder continues to use port 3000.
set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
agent_python="$project_root/.venv/bin/python"
if [[ ! -x "$agent_python" ]]; then
    printf '%s\n' "请先在仓库根目录运行 uv sync --frozen，安装 Agent 专用环境。" >&2
    exit 1
fi

runtime_dir="${XDG_STATE_HOME:-$HOME/.local/state}/ai4s-workbench-demo"
mkdir -p "$runtime_dir"
printf '%s\n' "$$" > "$runtime_dir/server.pid"

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

python "$project_root/scripts/serve_workbench.py" \
    --host 127.0.0.1 --port 3001 --data-dir "$runtime_dir/api-state" &
workbench_pid=$!
service_pids+=("$workbench_pid")

"$agent_python" "$project_root/scripts/run_agent_demo.py" \
    --host 127.0.0.1 --port 3002 --root-path /agent &
agent_pid=$!
service_pids+=("$agent_pid")

PYMOL_RPCHOST=127.0.0.1 NOVNC_HOST=127.0.0.1 \
    bash "$project_root/tools/pymol_web/start.sh" \
    -r "$project_root/tools/pymol_web/workspace.py" "$@" &
service_pids+=("$!")

nginx -p "$runtime_dir/" -c "$project_root/tools/pymol_web/workspace-nginx.conf" &
proxy_pid=$!
service_pids+=("$proxy_pid")

# Closing PyMOL leaves the workbench available. Exiting this launcher cleans up
# only its own children; it does not control Coder or the workspace container.
wait -n "$workbench_pid" "$agent_pid" "$proxy_pid"
