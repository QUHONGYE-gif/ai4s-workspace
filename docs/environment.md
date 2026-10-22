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

下述团队科研服务器与个人 Coder 工作区尚未建立蛋白质生成模型环境。服务器已有 Cellist 环境仅作为已有资源记录，不表示它适用于本项目。单独租用实例的试运行环境见本节末尾；其成功不代表团队环境已经配置。

### 个人 Coder 工作区核验（2026-10-21）

个人 `ckz/dev` 工作区的远程命令与仓库读写已验证。工作区为 Linux x86_64，仓库位于容器用户目录；联网曾使用个人电脑反向代理隧道，依赖该电脑和隧道在线，不是团队常驻网络服务。核验时没有可用 GPU，未检测到已安装的 Conda；共享数据卷剩余约 2.0 GiB。这是 2026-10-21 当时状态，后续资源应重新检查，不能认为该工作区已具备完整蛋白质模型环境。远程控制使用 Coder CLI；容器内试装的 Codex CLI 已按要求移除。

### 矩池云临时 GPU 试运行（2026-10-21）

陈铠洲单独租用 Linux x86_64、RTX 4090（24564 MiB，驱动 565.77）实例完成 R001/R002/R003。该实例与 `lab-gpu`、团队 Coder 工作区是不同执行环境。

| 项目 | 当时的实际配置及边界 |
| --- | --- |
| 计算与存储 | 单张 4090；实例盘初始约 300 GB；`/mnt` 持久卷容量 5 GB |
| 数据根目录 | `/root/ai4s-trial`，仅为此次租用实例的执行路径，不是团队统一目录 |
| RFdiffusion／ProteinMPNN | Conda `rfd4090`，Python 3.10.22，PyTorch 2.0.1+cu118；完整版本、源码提交和兼容修复见 [R001](../experiments/R001-protein-design-smoke/record.md#执行身份) |
| Boltz | 镜像环境 `myconda`，Python 3.11.13、Boltz 2.2.1、PyTorch 2.6.0+cu124；关闭可选 kernels |
| 代码入口 | [控制脚本](../scripts/protein_design_pipeline.py) 与 [实际配置](../configs/protein_design.matpool.json)；路径调整方法见 [团队使用说明](protein_pipeline.md#a1-已验证-cpu-封装的使用方式) |
| 运行证据 | [R001](../experiments/R001-protein-design-smoke/record.md)、[R002](../experiments/R002-swissprot-msa/record.md)、[R003](../experiments/R003-pipeline/record.md) 维护各自归档身份；Git 提供小型附件选集 |
| 完整归档 | 陈铠洲保管，已备份至平台持久卷；尚未上传团队共享存储，暂无统一下载链接 |

租用平台持久卷备份目录为 `/mnt/ai4s-trial-20261021/`，R001 另有 `/mnt/ai4s-trial-20261021.tar.gz`。这是原账户下的备份位置，不代表其他成员可直接访问。平台[持久卷说明](https://www.matpool.com/supports/doc-quick-start)称 `/mnt` 映射同区域个人网盘，释放实例后网盘保留；本次另校验了回传副本，不单独依赖临时实例。

关机准备另保存 `ai4s-recovery-20261021.tar.gz`：38,067,041 字节，358 个条目，SHA-256 `5123f78c6d243037f0679002cd5e828156f572d5d7d3c9842660c5e522f378e9`。原实例、持久卷和回传副本校验一致。它包含 RFdiffusion／ProteinMPNN 源码、SE3-Transformer 相关代码、已有 schedules、安装日志、输入、控制脚本及两个 Conda 环境的 `env export`、`list --explicit`；Git 提交信息另存。**这不是整机镜像或可直接解压运行的 Conda 环境。**

原始模型权重、Boltz 分子资料、可重建的解压数据库和整个 Conda 安装目录未纳入恢复包。恢复时需重新安装依赖、下载并校验权重/资料、重建搜索库，再做兼容性验证。已使用权重哈希在 [R003 原始清单](../experiments/R003-pipeline/evidence/manifest.json)；Boltz 亲和力权重未用于本次结构预测。尚未替团队部署 GPU 环境，也未代替用户关闭或释放租用实例。

### 租用实例关机前复核（2026-10-22）

已重新核验本机保存的 R001、R002、R003、CPU 阳性补查、R004 完整包、源码审阅包及源码／环境恢复包，均匹配既有记录的大小和 SHA-256。远端 R004 清单的 206 个条目无变化；恢复包中小于 2 MB 的源码文件与现有副本比对无变化。检查时没有 GPU 计算进程或 tmux 会话；未代替用户关机。

补查发现 CPU 搜索库／临时文件、GPU MMseqs2 原始发布包、最后归档日志，以及源码目录内 RFdiffusion Hydra 配置／日志等尚未完整回传，已新增以下独立补充包，实例与 `/mnt/ai4s-trial-20261021/` 副本哈希一致：

| 补充包 | 内容 | 字节数 | SHA-256 |
| --- | --- | ---: | --- |
| `ai4s-shutdown-extra-20261022.tar.gz` | 62 个文件／链接条目：CPU DB/tmp、日志、脚本／配置、GPU 发布包与最后归档日志；包内另附清单 | 247,486,566 | `54b39bce052fed250e2d246497c4e2d1ad7072688c692da33ec0794ba4fc0faf` |
| `ai4s-source-generated-20261022.tar.gz` | 53 个文件：RFdiffusion Hydra 配置／日志、ProteinMPNN 官方示例输出；包内另附清单 | 636,205 | `704fed74d93891807881928fcd305722b0f166d51340b21e2461f99f23d19b4c` |

**这两份补充包尚未到本机**：自动与用户手动下载均被浏览器标记为“已被您的组织屏蔽”，停止下载尝试，未修改安全设置。它们目前依赖同区域个人网盘，关闭或释放计算实例时须保留该网盘；后续通过获准通道回传并再次核验。已有正式实验归档已在本机，但不能据此声称全部服务器材料均已本地备份。完整 Conda 安装、大型模型权重和 Boltz 缓存仍未整体备份，恢复需重新准备。本机私有复核记录为 `.local/matpool/shutdown-audit-20261022.json`。

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
