# 环境与执行约定

## 配置来源与状态

用户于 2026-10-18 指定服务器配置与“空间组转录正式试验”一致。以下服务器信息来自该项目的 `AGENTS.md` 和 `docs/environment.md`；已于本轮连接服务器并核查 Docker 与资源；本地原型保留，服务器部署进度见状态文件。

本地仓库为 `/Users/quhongye/Documents/ChatGPT/大创`。当前实施状态统一见 [status.md](status.md)。

## 已有本地原型

用户已指定使用本地 Docker + Coder；系统 `lab` Conda 环境可用于辅助脚本。以下是本轮实际检查及配置：

| 项目 | 信息 |
| --- | --- |
| 宿主机 | macOS，Apple Silicon `arm64` |
| Docker | Docker Desktop 4.81.0；Engine 29.6.1；context `desktop-linux` |
| Compose | v5.2.0；项目 `ai4s-local`，网络同名 |
| 本地 Conda | `/opt/homebrew/Caskroom/miniforge/base/envs/lab`，Python 3.11.14；本轮未新增包 |
| Coder | 2.38.0，Linux ARM64；控制面在 Docker 内运行 |
| PostgreSQL | 17.11，Linux ARM64；专用于 Coder，不作为科学产物目录 |
| Terraform 与 provider | Terraform 1.16.2；coder 2.19.0、docker 3.9.0，依赖锁文件在工作区模板目录 |
| 开发镜像 | `ai4s-workspace:0.1.0`；Python 3.12.15、Git 2.47.3、curl 8.14.1 |
| 本机网页入口 | `http://localhost:7080`，端口仅发布到 `127.0.0.1` |
| 数据库与控制面卷 | `ai4s-local_database`、`ai4s-local_coder_home` |
| 工作区 | 已创建 `local-admin/prototype`；模板 `local-docker`；`/workspace/project` 挂载本地仓库；每个工作区有独立 home 卷 |
| 共享数据 | Docker 命名卷 `ai4s-local_shared`，在工作区挂载为 `/shared` |
| 本地私有配置与记录 | `.env` 保存初始凭据；`.local/` 保存日志和验证记录，两者均忽略于 Git |

宿主机 `lab` 是 macOS 环境，容器使用自身的 Linux Python，不将宿主机 Conda 环境直接挂入容器。当前使用 CPU 开发底座，不代表 RFdiffusion、ProteinMPNN、AlphaFold／Boltz 或 GPU 路径已验证。

Coder 控制面通过 Docker socket 创建工作区；已核对 Docker Desktop VM 中 socket 为 `root:root`、模式 660，控制面使用附加组 0。具体配置由 [compose.yaml](../compose.yaml) 维护。

已有镜像拉取通道出现 EOF。本轮经本机现有网络下载官方镜像，验证各层 SHA-256 后使用 `docker load` 导入；Coder 实际版本通过镜像内 CLI 核对，PostgreSQL 使用 Google 的 Docker Hub 公共缓存。容器和构建使用的本地代理只记录在 `.env`，未更改全局路由。Terraform provider 通过本机下载并校验后保存在项目镜像目录；模板可使用本地缓存安装。实际检查见 `.local/initialization.json`，日常操作见 [本地运行说明](local_docker.md)。

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

个人开发使用独立 `server-personal` 模板，代码保存在各工作区 home 卷的 `/home/coder/ai4s-workspace`；下表中的原型工作区继续保留。成员开户与种子目录统一见 [成员操作说明](members.md)。

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
| 控制面卷 | `ai4s-server_database`、`ai4s-server_coder_home`；数据库仍使用服务器原生初始化的 `coder` 库 |
| 私有凭据 | 远程副本 `.env`；本地备份 `.local/remote/.env`，权限 600 |
| 资源检查 | 部署前系统盘仅余约 562 MB，`/data1` 约 33 GB；因此采用独立数据目录，不迁移共享 Docker |

初始化与连接验证记录位于远程副本 `.local/`，回传记录保存在本机 `.local/remote/`（`initialization.json`、`deployment-inventory.json`、`api-status.json`）；操作统一见 [服务器运行说明](server_docker.md)。

日常同步方向为本地代码到远程执行副本；小型指标、图表与运行记录从远程回传本地。同步前检查两端差异，保护未提交修改及既有结果；不包含原始数据、环境、缓存或大型产物。

服务器执行、GPU 检查、数据保护和日志规则统一见 [AGENTS.md](../AGENTS.md)，不在此重复。实际实验的代码／配置／依赖／命令／种子及输出身份写入对应运行记录。

相关文档：[服务器运行说明](server_docker.md) · [本地运行说明](local_docker.md) · [实施计划](implementation_plan.md) · [设计草案](research_plan.md) · [状态](status.md) · [配置来源](workflow_sources.md) · [仓库入口](../README.md)。
