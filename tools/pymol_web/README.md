# PyMOL 接入现有工作台

PyMOL 桌面嵌入已有工作台的“常用工具 → PyMOL”页面。它与工作台运行在**同一个个人 Coder 容器**，共用原 3000 端口与“开发预览”；不新增容器、Coder 应用或模板资源。

在页面选择真实 `.pdb`、`.cif` 或 `.mmcif` 文件（最大 1 MiB），点击“加载到 PyMOL”。默认简洁模式隐藏 noVNC 工具栏、Linux 桌面栏和 PyMOL 原生命令区，分子视图填满展示窗口。右上“真实工具”左侧的“完整界面”开关恢复 PyMOL 菜单、对象面板和原生命令区，切换时保留同一会话与分子。

下方网页命令框执行原生 PyMOL 命令，例如 `color cyan, all`、`count_atoms all`。按 Enter 或点击“执行”，反馈、查询结果及错误显示在可折叠的“执行输出”中；使用上下方向键或历史列表调用最近 50 条命令，历史在当前页面会话内保留。命令按本人工作区权限执行，完整界面中的其他原生操作照常可用。

视图中可旋转、缩放和选择原子；右侧可切换卡通、球棍、线框和表面。工作流目录仍为模拟数据，不会冒充真实结构文件。同工作区的浏览器共用一个 PyMOL 会话，重新加载只替换网页管理的 `browser_structure` 对象。

## 安装与启动

在现有 Debian 13 个人容器内安装系统包，不需要 Docker socket 或重新构建镜像：

```bash
apt-get update
apt-get install -y --no-install-recommends \
  pymol xvfb x11-utils x11vnc novnc websockify fluxbox \
  fonts-dejavu-core libgl1-mesa-dri nginx-light
```

服务器下载慢时，在本地中转同版本 Debian 的官方索引及依赖包，由容器内 APT 校验签名并安装；不混用 Ubuntu 包，也不关闭签名校验。中转完成后删除临时下载副本。

先结束本人原有工作台服务，再从仓库根目录启动：

```bash
bash tools/pymol_web/start-workspace.sh
```

保持进程运行，打开原“开发预览”，进入已有 PyMOL 页面。关闭 PyMOL 不会停止工作台；需要重新打开工具时，结束本人这次启动的服务并重新执行上面的命令。后台运行时可沿用原运行目录的 `server.log`；启动器把自身 PID 写入 `server.pid`。

## 文件与进程分工

- `start.sh`：启动 Xvfb、Fluxbox、PyMOL、x11vnc 与 websockify，退出时清理自己启动的进程。
- `start-workspace.sh`：启动原 Python 服务（内部 3001）、PyMOL 与路径代理。
- `workspace-nginx.conf`：原 3000 端口代理工作台，`/tools/pymol/` 代理桌面与 WebSocket。
- `workspace.py`：在 PyMOL 内运行，切换原生界面、执行命令并读取该次真实反馈；Qt 操作在 GUI 线程完成。
- `src/workbench/pymol.py`：通过 PyMOL 内置的回环 XML-RPC 接口加载文件、切换显示与执行命令。
- `web/demo/pymol.html`：直接使用已有 noVNC 客户端显示桌面，不增加 noVNC 工具栏。

VNC、noVNC、XML-RPC 和工作台内部端口均只监听容器回环地址；访问权限沿用 Coder 原个人预览。上传文件保存在原服务数据目录旁的 `pymol-inputs/`，以唯一名称保留，原模拟快照目录继续使用 `api-state/`。此接入只提供结构查看，不执行蛋白质生成或证明科学模型有效。

代码和上传文件位于 home 持久卷；原地安装的系统依赖在容器**重建**后需要重新安装。工作区停止后服务进程也需重新启动。本实现不自动重建容器或改动模板。

历史独立镜像的 `Dockerfile` 仍保留；本次接入不使用独立容器，也不重新构建该镜像。

依据：[PyMOL 内置 RPC](https://github.com/schrodinger/pymol-open-source/blob/master/modules/pymol/rpc.py) · [noVNC 嵌入](https://github.com/novnc/noVNC/blob/master/docs/EMBEDDING.md) · [Nginx WebSocket 代理](https://nginx.org/en/docs/http/websocket.html)。

返回：[仓库入口](../../README.md) · [蛋白质设计程序](../../docs/protein_pipeline.md)。
