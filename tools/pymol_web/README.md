# PyMOL 网页容器

容器运行 Ubuntu 开源版 PyMOL，通过 Xvfb、Fluxbox、x11vnc 和 noVNC 提供结构查看界面，使用软件 OpenGL 渲染，无需 GPU。软件来源为 [Ubuntu PyMOL 包](https://packages.ubuntu.com/jammy/pymol)、[开源 PyMOL](https://github.com/schrodinger/pymol-open-source) 和 [noVNC](https://github.com/novnc/noVNC)；各组件遵循自己的许可证。

## 构建与访问

在已安装并运行 Docker 的电脑或获准使用的 Docker 宿主机上，从仓库根目录执行：

```bash
docker build -t ai4s-pymol-web tools/pymol_web
mkdir -p .local/pymol-data
docker run --rm --name ai4s-pymol-web \
  -p 127.0.0.1:16080:6080 \
  --mount type=bind,src="$(pwd)/.local/pymol-data",dst=/data,readonly \
  ai4s-pymol-web
```

打开 [本机 noVNC](http://127.0.0.1:16080/vnc.html?autoconnect=true&resize=scale)。把 PDB/CIF 放入 `.local/pymol-data`，在 PyMOL 的 File → Open 中从 `/data` 加载；也可以在镜像名后传 `/data/example.pdb`，启动时直接打开。

输入目录默认只读。保存结果时，另挂载当前容器用户（UID 1000）可写的输出目录并在 PyMOL 中选该路径；未挂载目录中的文件随 `--rm` 容器退出而消失。镜像以普通用户运行，原始结构文件不修改。

容器中的原始 VNC 只监听回环地址。此用法依靠 Docker **宿主机的回环绑定**限制网页访问，无独立网页登录；保留命令中的 `127.0.0.1`，不直接发布到公网或不可信网络。关闭 PyMOL 会结束容器；也可执行 `docker stop ai4s-pymol-web`。

默认从 Ubuntu 官方源安装。源不可达时可在构建命令中传 `--build-arg UBUNTU_MIRROR=<可用的同架构Ubuntu镜像地址>`；amd64 对应 `ubuntu`，arm64 对应 `ubuntu-ports`。该选项也替换安全更新源，须选择及时同步的可信镜像，APT 签名校验保持启用。

## 远程使用与 Coder 边界

在获准的远程 Docker 宿主机启动同一命令后，在个人电脑做 SSH 转发：

```bash
ssh -N -L 16080:127.0.0.1:16080 <你的Docker宿主机>
```

浏览器仍访问本机地址。无需把 5900 或 6080 发布到公网。

当前个人 Coder 工作区不提供 Docker socket，不能直接照此构建嵌套容器；其开发预览目前只代理容器内 3000 端口。这份工具不会自动出现在 Coder 预览或工作台工具会话中。团队接入需由管理员另行安排，此 PR 不改变 Coder 权限和部署配置。

## 检查与排错

```bash
docker logs ai4s-pymol-web
docker exec ai4s-pymol-web xdpyinfo -display :0
docker exec ai4s-pymol-web python3 -c "from pymol import cmd; print(cmd.get_version())"
```

先确认网页可打开，再确认 PyMOL 桌面实际显示并能加载结构。端口已占用时只改宿主机端口 `16080`；挂载输入为空时检查 Docker 所在电脑的目录。启动脚本等待 X 显示就绪，任何服务退出都会清理其余进程，错误保留在容器日志中。

返回：[仓库入口](../../README.md) · [蛋白质设计程序](../../docs/protein_pipeline.md)。
