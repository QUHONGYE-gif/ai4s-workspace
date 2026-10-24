# PyMOL 接入工作台

在同一个个人 Coder 容器内运行 PyMOL，嵌入已有“常用工具 → PyMOL”页面，共用 3000 端口与开发预览。

## 使用

- 上传真实 `.pdb`、`.cif` 或 `.mmcif` 文件，最大 1 MiB。网页加载只替换 `browser_structure` 对象。
- 默认简洁模式让分子视图填满窗口；“真实工具”左侧的“完整界面”开关恢复原生菜单、对象面板和命令区，继续使用同一会话。
- 下方命令框执行原生命令，例如 `count_atoms all`；Enter 执行，上下方向键或历史列表调用最近 50 条命令，输出可折叠。历史在当前页面会话内保留。
- 同一工作区的页面共用 PyMOL。命令按本人工作区权限执行；工作流目录仍为模拟，不会自动提供真实结构。

## 安装与启动

使用与容器发行版配套的系统包。以下适用于 Debian 13：

```bash
apt-get update
apt-get install -y --no-install-recommends \
  pymol xvfb x11-utils x11vnc novnc websockify fluxbox \
  fonts-dejavu-core libgl1-mesa-dri nginx-light
```

确认并结束本人已有的 3000 端口应用后，从仓库根目录启动：

```bash
bash tools/pymol_web/start-workspace.sh
```

不需要重建容器或新增 Coder 入口。网络受限时可中转同发行版、同架构的官方依赖，保留 APT 签名校验，完成后清理缓存。

## 维护

| 文件 | 职责 |
| --- | --- |
| [start-workspace.sh](start-workspace.sh) | 联合启动工作台、PyMOL 与路径代理 |
| [start.sh](start.sh) | 管理 Xvfb、窗口管理器、PyMOL 和 VNC 子进程 |
| [workspace.py](workspace.py) | 在 PyMOL GUI 线程切换界面、执行命令并读取反馈 |
| [workspace-nginx.conf](workspace-nginx.conf) | 3000 代理工作台内部 3001 及 noVNC 路径 |
| [后端接口](../../src/workbench/pymol.py) | 回环 RPC 与结构加载 |
| [嵌入页面](../../web/demo/pymol.html) | 复用已有 noVNC 客户端 |

内部端口仅监听回环地址，访问权限沿用个人预览。运行目录为 `${XDG_STATE_HOME:-$HOME/.local/state}/ai4s-workbench-demo`；`api-state/` 保存模拟快照，`pymol-inputs/` 保存上传文件，`server.log`、`server.pid` 用于管理启动进程。

关闭 PyMOL 不停止工作台；重新打开工具需重启本人启动的联合服务。工作区停止后需重新启动服务，容器重建后需重新安装系统依赖；需保留的文件放在持久卷。

接口依据：[PyMOL RPC](https://github.com/schrodinger/pymol-open-source/blob/master/modules/pymol/rpc.py) · [noVNC](https://github.com/novnc/noVNC/blob/master/docs/API.md) · [Nginx WebSocket](https://nginx.org/en/docs/http/websocket.html)。

返回 [仓库入口](../../README.md) · [前后端开发](../../web/README.md)。
