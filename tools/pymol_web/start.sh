#!/bin/bash
set -e

# 启动VNC服务，无密码访问
x11vnc -display :0 -bg -forever -nopw -quiet

# 启动轻量窗口管理器Fluxbox
fluxbox &

# 启动noVNC网页转发，把VNC转为网页访问
websockify --web=/usr/share/novnc ${NOVNC_PORT} localhost:${VNC_PORT}

wait