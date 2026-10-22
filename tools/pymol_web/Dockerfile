FROM ubuntu:22.04
LABEL maintainer="AI4S大创项目 计算生物学工具组"
LABEL tool="pymol-open-source-web"
LABEL description="Open-Source PyMOL + noVNC 网页可视化容器，用于蛋白结构查看处理"

# 避免交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 安装系统依赖：vnc、novnc、桌面环境、编译依赖、python
RUN apt update && apt install -y \
    x11vnc novnc websockify fluxbox xterm \
    python3 python3-pip python3-dev \
    build-essential libpng-dev libfreetype6-dev libxml2-dev \
    libglut-dev libglew-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装开源PyMOL
RUN pip3 install pymol-open-source

# VNC & noVNC 端口配置
ENV DISPLAY=:0
ENV VNC_PORT=5900
ENV NOVNC_PORT=6080

# 拷贝启动脚本
COPY start.sh /start.sh
RUN chmod +x /start.sh

# 对外暴露网页端口
EXPOSE 6080

# 启动入口
CMD ["/start.sh"]