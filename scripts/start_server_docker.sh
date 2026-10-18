#!/bin/sh
# Run on lab-gpu as qhy. Uses existing system binaries; never touches system Docker.
set -eu
test "$(id -un)" = qhy
task_root=/data1/qhy/docker-ai4s
mkdir -p "$task_root/data" "$task_root/run" "$task_root/tmp" "$task_root/logs"
chmod 700 "$task_root" "$task_root/run"
if [ ! -f "$task_root/daemon.json" ]; then
  cat > "$task_root/daemon.json" <<'JSON'
{
  "log-driver": "local",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "cgroup-parent": "ai4s.slice"
}
JSON
fi
mkdir -p "$HOME/.config/systemd/user"
task_slice="$HOME/.config/systemd/user/ai4s.slice"
if [ ! -f "$task_slice" ]; then
  cat > "$task_slice" <<'SLICE'
[Unit]
Description=AI4S Docker and containers combined resource budget

[Slice]
MemoryMax=6G
CPUQuota=200%
TasksMax=4096
SLICE
fi
task_unit="$HOME/.config/systemd/user/ai4s-docker.service"
if [ ! -f "$task_unit" ]; then
  cat > "$task_unit" <<'UNIT'
[Unit]
Description=AI4S project rootless Docker on data1

[Service]
Slice=ai4s.slice
Type=simple
Environment=PATH=/usr/sbin:/usr/bin:/sbin:/bin
Environment=XDG_RUNTIME_DIR=/run/user/1029
Environment=TMPDIR=/data1/qhy/docker-ai4s/tmp
Environment=DOCKER_TMPDIR=/data1/qhy/docker-ai4s/tmp
WorkingDirectory=/data1/qhy
ExecStart=/usr/share/docker.io/contrib/dockerd-rootless.sh --config-file=/data1/qhy/docker-ai4s/daemon.json --data-root=/data1/qhy/docker-ai4s/data --exec-root=/data1/qhy/docker-ai4s/run/exec --pidfile=/data1/qhy/docker-ai4s/run/docker.pid --host=unix:///data1/qhy/docker-ai4s/run/docker.sock
Delegate=yes
MemoryMax=6G
CPUQuota=200%
TasksMax=4096
Restart=on-failure
RestartSec=5
TimeoutStopSec=90
KillMode=mixed
StandardOutput=append:/data1/qhy/docker-ai4s/logs/daemon.log
StandardError=append:/data1/qhy/docker-ai4s/logs/daemon.log

[Install]
WantedBy=default.target
UNIT
fi
systemctl --user daemon-reload
systemctl --user enable --now ai4s-docker.service
for attempt in $(seq 1 30); do
  if docker --host "unix://$task_root/run/docker.sock" info --format 'Root={{.DockerRootDir}} Security={{json .SecurityOptions}}'; then
    exit 0
  fi
  sleep 1
done
echo "Docker did not become ready; inspect $task_root/logs/daemon.log" >&2
exit 1
