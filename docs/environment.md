# 环境与执行约定

使用服务器端coder+Docker的形式进行开发

Coder 控制面通过 Docker socket 创建工作区；Docker Desktop VM 中 socket 为 `root:root`、模式 660，控制面使用附加组 0。具体配置由 [compose.yaml](../compose.yaml) 维护。

已有镜像拉取通道出现 EOF。本轮经本机现有网络下载官方镜像，验证各层 SHA-256 后使用 `docker load` 导入；Coder 实际版本通过镜像内 CLI 核对，PostgreSQL 使用 Google 的 Docker Hub 公共缓存。容器和构建使用的本地代理只记录在 `.env`，未更改全局路由。Terraform provider 通过本机下载并校验后保存在项目镜像目录；模板可使用本地缓存安装。实际检查见 `.local/initialization.json`，日常操作见 [本地运行说明](operations.md#本地原型恢复)。

## 服务器配置

| 项目 | 信息 |
| --- | --- |
| 连接方式 | `ssh lab-gpu` |
| 远程用户 | `qhy` |
| 用户主目录 | `/home1/qhy`，不用于大型实验文件 |
| 数据根目录 | `/data1/qhy` |
| Conda 安装 | `/data1/qhy/miniforge3` |
| 已有环境 | base；`/data1/qhy/miniforge3/envs/Cellist` |
| tmux | `/usr/bin/tmux` |
| 既有数据与实验目录 | `/data1/qhy/raw_data`、`/data1/qhy/projects`、`/data1/qhy/reproduction` |
| 既有复现代码目录 | `/data1/qhy/projects/Cellist`、`/data1/qhy/projects/Cellist_Evaluation` |

上述 Conda 与既有实验路径继续作为参考配置；本轮只核验服务器身份、Docker 和本项目目录，不把它们描述为已验证的蛋白质环境。

## 本项目环境与同步位置

下表维护服务器原型与控制面的部署位置；正式成员使用下方的 [个人工作区](#个人工作区)，开户及更新步骤见 [部署与运维](operations.md)。

蛋白质生成工具的依赖、模型权重、科学数据库和工作台业务前后端环境尚未检查或建立。服务器已有 Cellist 环境仅作为已有资源记录，不表示它适用于本项目；准备阶段核查实际兼容性后，再补充本项目环境路径与用途。

本轮已创建的服务器位置与核验结果：

| 项目 | 信息 |
| --- | --- |
| 宿主平台 | Linux x86_64；用户 qhy，UID 1029、GID 1030 |
| 既有 Docker | Engine 20.10.24+dfsg1，Compose v2.40.0；系统 socket 保持原样 |
| 本项目代码副本 | `/data1/qhy/projects/ai4s-workbench/repo` |
| 独立 Docker | 用户服务 `ai4s-docker.service`，rootless、systemd cgroup v2 |
| 数据根目录 | `/data1/qhy/docker-ai4s/data`，包含镜像、容器、卷和缓存 |
| 独立 socket | `/data1/qhy/docker-ai4s/run/docker.sock` |
| 导入临时文件与日志 | `/data1/qhy/docker-ai4s/tmp`、`/data1/qhy/docker-ai4s/logs` |
| 资源上限 | `ai4s.slice` 中守护进程与容器合计 2 核 CPU、6 GiB 内存；无 GPU 分配 |
| Coder／数据库 | Coder 2.38.0；PostgreSQL 17.11，均为 Linux AMD64 |
| 开发镜像 | `ai4s-workspace:server-0.1.0`；Python 3.12.15、Git 2.47.3、curl 8.14.1 |
| 工作区 | `server-admin/prototype`，模板 `server-docker`；容器 `ai4s-server-server-admin-prototype` |
| 仓库与持久化 | `/workspace/project` 挂载远程代码副本；独立 home 命名卷、`ai4s-server_shared` 共享卷均在上述数据根目录 |
| HTTPS 接入 | 两端位置见下方 [HTTPS 中转](#https-中转位置)，证书与通道操作见 [部署与运维](operations.md#https-接入) |
| 控制面卷 | `ai4s-server_database`、`ai4s-server_coder_home`；数据库仍使用服务器原生初始化的 `coder` 库 |
| 私有凭据 | 远程副本 `.env`；本地备份 `.local/remote/.env`，权限 600 |
| 资源检查 | 部署前系统盘仅余约 562 MB，`/data1` 约 33 GB；因此采用独立数据目录，不迁移共享 Docker |

初始化与连接验证记录位于远程副本 `.local/`，回传记录保存在本机 `.local/remote/`（`initialization.json`、`deployment-inventory.json`、`api-status.json`）；操作统一见 [服务器运行说明](operations.md#服务器部署)。

## 个人工作区

| 项目 | 位置与配置 |
| --- | --- |
| 模板与工作区 | `server-personal`；每位成员使用自己的 `dev`，代码与登录规则见 [成员指南](collaboration.md) |
| 代码与 home 卷 | `/home/coder/ai4s-workspace`，卷名 `ai4s-personal-<workspace-id>-home`，位于独立 Docker 数据目录 |
| 公开 Git 种子 | 宿主机 `/data1/qhy/projects/ai4s-workbench/member-seed/repository.bundle`；容器只读挂载 `/opt/ai4s-seed` |
| 共享产物 | `ai4s-server_shared` 卷挂载到 `/shared` |
| 单工作区资源 | 1 核、1 GiB；所有实例仍受上表 `ai4s.slice` 总量限制，无 GPU 分配 |
| 成员私有记录 | 本地 `.local/members/` 保存已交付账号的邮箱和独立初始密码，文件权限 `600`，不入 Git |

## 工作台模拟网页与本地 Coder CLI

2026-10-18 将用户指定的 HTML 载入 `qhy/dev`，随后拆为前端资源与 Python 模拟状态 API；文件分工见 [前后端开发说明](../web/README.md)，使用方式见 [成员指南](collaboration.md#工作台模拟网页)。未修改模板、控制面或 Docker 配置，未部署真实科研执行或成员共享后端。

| 项目 | 位置与实际配置 |
| --- | --- |
| 远程网页 | `qhy/dev` 容器内 `/home/coder/ai4s-workspace/web/demo/index.html`，处于个人 home 持久卷 |
| 服务 | 容器已有 Python 3.12.15；运行 `scripts/serve_workbench.py`，监听 `127.0.0.1:3000`，同源提供 `web/demo` 与 `/api/` |
| 个人 HTTPS 预览 | [qhy 开发预览](https://coder.my-rustdesk.xyz/@qhy/dev.dev/apps/preview/)，沿用本人访问权限 |
| 模拟快照 | `/home/coder/.local/state/ai4s-workbench-demo/api-state/`，按浏览器命名空间隔离的 JSON，不入 Git |
| 远程日志与身份记录 | `/home/coder/.local/state/ai4s-workbench-demo/server.log`、`deployment.json`、`server.pid` |
| 本机访问 | [http://127.0.0.1:18080/](http://127.0.0.1:18080/)，由 Coder CLI 转发到上述容器端口 |
| 本机 CLI | `.local/tools/coder/coder`，macOS ARM64 slim 版 `v2.38.0+c3c6a67`，与服务端一致 |
| CLI 来源 | 现有 Coder 服务的 HTTPS `/bin/coder-darwin-arm64`；文件 SHA-1 与响应 ETag 一致，SHA-256 见本地验证记录 |
| CLI 入口与配置 | [scripts/coder-cli.sh](../scripts/coder-cli.sh)；独立配置 `.local/tools/coder/config/`，已以 qhy 登录，不修改系统级配置 |
| 本机转发记录 | `.local/workbench-demo/port-forward.json`、`port-forward.log`；服务和转发为后台进程，未设置开机自启 |
| 私密验收证据 | `.local/workbench-demo/`，包含部署、HTTPS／匿名拒绝、本机转发及浏览器验收记录，不入 Git |

当前为多文件版本；逐文件摘要与部署身份保存于远程 `deployment.json` 及本地 `.local/frontend-backend-split/`。原单文件备份在远程运行目录的 `before-frontend-backend-split/`。CLI 与登录配置只位于本机，不同步到成员工作区。

Coder CLI 转发语法依据 [官方端口转发说明](https://coder.com/docs/reference/cli/port-forward)，本项目实际命令见成员指南。此访问方式用于开发与体验检查，不代表独立正式业务入口或真实多人共享后端已完成。

### PyMOL 结构查看

2026-10-24 在 qhy 现有个人容器内原地安装并接入，未重新构建镜像或改变 Coder 模板。已有工作台的 PyMOL 页面直接嵌入真实桌面；工作流和共享目录本身仍为模拟。

| 项目 | 实际配置 |
| --- | --- |
| 系统依赖 | Debian 13 官方 APT 包；PyMOL 3.1.0、noVNC 1.6.0、Nginx 1.26.3，使用软件 OpenGL |
| 启动入口 | `bash tools/pymol_web/start-workspace.sh`，从个人仓库根目录运行 |
| 访问入口 | 原 `qhy/dev` 的“开发预览”内 `#/tools/pymol`，未新增 Coder 应用 |
| 内部连接 | 3000 路径代理原工作台 3001 与 noVNC 6080；VNC 5900、PyMOL RPC 9123；均只监听容器回环地址 |
| 状态与上传 | 原 `api-state/` 沿用；上传结构保存在同级 `pymol-inputs/`，都位于 `/home/coder/.local/state/ai4s-workbench-demo/` |
| 日志与进程 | 沿用同目录 `server.log`、`server.pid` 和 `deployment.json`，只管理本人应用子进程 |

系统包通过本地中转官方索引和依赖，由容器内 APT 验证签名后安装；未改原 Debian 源配置。代码与上传文件在 home 卷中保留，容器被重建或替换后需要重新安装系统依赖，应用进程需手动启动；本次未增加自动重建或模板部署机制。安装命令和使用方式见 [PyMOL 说明](../tools/pymol_web/README.md)。

## HTTPS 中转位置

成员入口为 [https://coder.my-rustdesk.xyz](https://coder.my-rustdesk.xyz)。用户确认根域名已备案、用途为成员个人开发；这不是平台备案审查结论。访问链路为：

```text
成员浏览器 → coder.my-rustdesk.xyz:443 → 阿里云 Nginx
  → 中转机 127.0.0.1:27080 → 常驻 SSH 反向转发
  → lab-gpu 127.0.0.1:17080 → Docker 中的 Coder
```

阿里云中转机仅承载接入，不运行模型计算：`ssh root@47.109.63.27`，成都 `cn-chengdu`，Ubuntu 26.04。科研服务器不保存该机 root 凭据；运维步骤见 [HTTPS 接入](operations.md#https-接入)。

| 位置 | 配置与约束 |
| --- | --- |
| 阿里云 DNS | `coder` A 记录指向 `47.109.63.27`，TTL 600 秒；根域名记录保留 |
| 中转账号 | `ai4s-tunnel`，home `/var/lib/ai4s-tunnel`，shell `nologin`；`.ssh/authorized_keys` 限制 `permitlisten="127.0.0.1:27080"` |
| SSH 限制 | `/etc/ssh/sshd_config.d/60-ai4s-tunnel.conf`，只允许指定远程转发，禁止会话及其他转发 |
| Nginx | `/etc/nginx/sites-available/coder.my-rustdesk.xyz`，由 `sites-enabled` 同名链接启用；原网站配置保留 |
| ACME webroot | `/var/lib/ai4s-coder/acme`，该目录及父目录权限 `755` 以便 Nginx 遍历；只存公开挑战文件 |
| 证书与续期 | `/etc/letsencrypt/live/coder.my-rustdesk.xyz/`，私钥只留云服务器；沿用 `certbot.timer`，部署钩子 `/etc/letsencrypt/renewal-hooks/deploy/ai4s-coder-reload` |
| 中转配置准备副本 | `/opt/ai4s-coder/preparation`；初始 HTTP Nginx 备份 `/opt/ai4s-coder/nginx-http.before` |
| 接入日志 | `/var/log/nginx/ai4s-coder-access.log`，只记路径、不记查询参数；错误日志为同目录 `ai4s-coder-error.log` |
| 科研服务器通道密钥 | `/data1/qhy/coder-relay/`，目录 `700`、私钥 `600`，独立私钥不出科研服务器；主机公钥经已认证的云服务器 SSH 会话取得并固定 |
| 科研服务器用户服务 | `~/.config/systemd/user/ai4s-coder-relay.service`，归入 `ai4s.slice`，自身上限 0.25 核、128 MiB，沿用 linger |
| Coder 切换前配置 | 服务器项目副本 `.local/aliyun-relay/env.before`；真实 `.env` 保留在服务器 |

日常同步方向为本地代码到远程执行副本；小型指标、图表与运行记录从远程回传本地。同步前检查两端差异，保护未提交修改及既有结果；不包含原始数据、环境、缓存或大型产物。

服务器执行、GPU 检查、数据保护和日志规则统一见 [AGENTS.md](../AGENTS.md)，不在此重复。实际实验的代码／配置／依赖／命令／种子及输出身份写入对应运行记录。

相关文档：[服务器运行说明](operations.md#服务器部署) · [本地运行说明](operations.md#本地原型恢复) · [实施计划](implementation_plan.md) · [设计草案](research_plan.md) · [状态](status.md) · [配置来源](workflow_sources.md) · [仓库入口](../README.md)。
