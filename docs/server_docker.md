# 服务器 Docker + Coder 运行说明

本文件维护服务器部署与操作；当前状态见 [状态](status.md)，路径与资源信息见 [环境](environment.md)。本地原型仍按 [本地运行说明](local_docker.md) 操作。

## 数据盘上的独立 Docker

本项目使用服务器已有的 rootless Docker 组件，直接指定数据根目录到数据盘。无需给共享 `/var/lib/docker` 建软链接，也不迁移、重启或清理共享 Docker。镜像、容器可写层、命名卷、构建缓存和导入临时文件均位于项目数据目录；用户服务声明是小文件，存于用户主目录。

[启动脚本](../scripts/start_server_docker.sh) 创建独立的 `ai4s-docker.service` 用户服务，复用已有 Docker 二进制；配置文件存在时保留。用户 linger 已启用，使服务在 SSH 登出后继续运行。`ai4s.slice` 将守护进程与容器的总量限制为 2 核、6 GiB 内存，容器另有各自上限。本轮是 CPU 开发环境，GPU 接入另按 [项目规则](../AGENTS.md) 处理。

在服务器上明确选择本项目 socket；不要用未指定 socket 的清理命令：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
docker info --format '{{.DockerRootDir}}'
docker compose -f compose.yaml -f compose.server.yaml ps
systemctl --user status ai4s-docker.service
```

本配置使用 rootless 用户映射：Coder 与工作区容器的 `0:0` 对应宿主机用户 `qhy`，因此可以读写该用户的仓库副本。容器中的 root 不是宿主机 root。仓库仅是本项目副本，共享 Docker socket 不挂入 Coder。

## 配置与初始化

- [基础 Compose](../compose.yaml) 维护共同服务定义；[服务器覆盖配置](../compose.server.yaml) 指定独立项目名、socket、用户和 CPU 上限。
- [共用模板](../coder/templates/local-docker/main.tf) 通过变量区分本地与服务器的网络、镜像及工作区用户，默认值保留本地设置；锁文件包含 ARM64 和 AMD64 校验值。
- [服务器配置示例](../.env.server.example) 只含占位值；服务器 `.env` 独立生成，保存管理员凭据及端口；本地私有备份在 `.local/remote/.env`，二者均不提交 Git。
- 服务持久卷保存在独立 Docker 数据根目录；每个工作区有独立 home，共享卷供 `/shared` 使用。

已有部署沿用现有 `.env`。仅首次创建配置时，在服务器仓库执行以下命令；文件已存在会退出，生成的密码不输出到终端：

```bash
python3 - <<'PY'
from pathlib import Path
import os
import secrets

text = Path('.env.server.example').read_text()
for key in ('POSTGRES_PASSWORD', 'CODER_BOOTSTRAP_PASSWORD'):
    text = text.replace(f'{key}=replace-with-a-random-password',
                        f'{key}={secrets.token_hex(24)}')
fd = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(text)
PY
```

首次创建独立 Docker 使用 `sh scripts/start_server_docker.sh`。该脚本针对当前 `qhy` / UID 1029、已有 rootless 组件及用户 systemd 环境；迁移到其他服务器须先核对 [环境](environment.md)。已有服务声明不会被脚本覆盖。

镜像及 provider 准备完成后，在服务器仓库运行：

```bash
python3 scripts/init_local_docker.py --server --skip-build
python3 scripts/check_local_docker.py --server
```

`--skip-build` 要求已经导入 `ai4s-workspace:server-0.1.0`。初次部署在本地构建 Linux AMD64 镜像后中转；服务器依赖镜像均使用实际核验版本。初始化只保留已有账户与数据库；验证会停止并启动 `prototype`，不要同时在该工作区开展其他任务。

Git 仓库不包含镜像或 provider 包。目前 Coder 镜像版本已在既有环境核验，但注册表同名标签的可拉取性不能由本地标签保证；新环境需要先准备并核验镜像。后续发布镜像与部署自动化的安排见 [CI/CD 接入计划](cicd.md)。

## 免成员隧道的 HTTPS 入口

已使用 [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)：服务器运行接入组件，成员直接在浏览器使用 HTTPS 地址及个人 Coder 账号，无需安装 Tailscale、Docker 或建立 SSH 隧道。公网入口受 Coder 登录和工作区权限控制；Funnel 本身不代替成员认证。它提供 `*.ts.net` 域名及 TLS，但有带宽限制，当前用于开发交互，大型数据仍在服务器内部处理。

采用独立的 [用户服务](../configs/ai4s-tailscale.service)，通过 userspace networking 运行，不更改宿主机网络路由，也不启用 Tailscale SSH 或子网路由。二进制、身份状态和 socket 均位于 `/data1/qhy/tailscale-ai4s/`。服务纳入现有 `ai4s.slice`，自身上限 0.25 核、256 MiB；现有项目总资源预算不增加。

部署顺序：

1. 从 [官方稳定包](https://pkgs.tailscale.com/stable/) 下载服务器 AMD64 静态包并核对官方 SHA-256。当前安装版本为 `1.104.1`；网络失败时从本地中转。将 `tailscale`、`tailscaled` 放入上述目录的 `bin/`，不覆盖已有安装。
2. 在服务器项目目录执行 `sh scripts/start_coder_funnel.sh`；[启动脚本](../scripts/start_coder_funnel.sh) 保留既有配置，内容不同则停止并要求核对。
3. 用下面的命令生成设备登录链接，由管理员在浏览器完成一次性认领。此时尚未发布 Coder 公网入口。

   ```bash
   /data1/qhy/tailscale-ai4s/bin/tailscale \
     --socket=/data1/qhy/tailscale-ai4s/run/tailscaled.sock \
     up --hostname=ai4s-coder --accept-dns=false --accept-routes=false --timeout=30s
   ```

4. 账号接入后，在 Tailscale 控制台按官方流程启用 HTTPS／Funnel。只代理 `http://127.0.0.1:17080`：

   ```bash
   /data1/qhy/tailscale-ai4s/bin/tailscale \
     --socket=/data1/qhy/tailscale-ai4s/run/tailscaled.sock \
     funnel --bg http://127.0.0.1:17080
   ```

5. 将实际 `https://...ts.net` 地址写为服务器 `.env` 的 `AI4S_PUBLIC_URL`，发布更新后的个人模板，再应用 [HTTPS 覆盖配置](../compose.funnel.yaml)。只重建控制面，保留数据库、工作区和持久卷；成员当前网页连接会短暂断开。

   ```bash
   export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
   docker compose -f compose.yaml -f compose.server.yaml -f compose.funnel.yaml up -d --no-deps coder
   ```

6. 从服务器外部验证证书、账号登录、网页终端及成员访问隔离后，才向成员分发入口。之后更新／重建控制面也须带上 `compose.funnel.yaml`；新工作区的 agent 使用 Docker 内部地址连接控制面。

撤回公网入口使用同一 socket 的 `tailscale funnel reset`，从服务器 `.env` 移除 `AI4S_PUBLIC_URL` 后，只对控制面执行不含 `compose.funnel.yaml` 的原 Compose 命令，即恢复旧访问配置。不要删除 Tailscale 身份状态、Coder 数据库或工作区卷。原有 SSH 隧道保留为管理员维护入口。实际完成情况及验证范围以 [状态](status.md) 为准。

## 访问

配置入口：[https://ai4s-coder.tail8b7421.ts.net](https://ai4s-coder.tail8b7421.ts.net)。**当前公网 DNS 尚未生效，暂不向未接入 Tailscale 的成员承诺可用；完成情况见 [状态](status.md)。**使用各自的 Coder 邮箱和密码，打开自己的 `dev` 工作区及 Terminal。成员无需安装 Tailscale／Docker、获取服务器 SSH 账号或建立隧道；GitHub 凭据和个人分支流程见 [成员操作说明](members.md)，合并遵循 [团队协作约定](collaboration.md)。

Docker 的 17080 端口仍只绑定服务器回环地址，Funnel 仅代理这一 Coder 服务；数据库、Docker socket 与其他服务器端口不发布。HTTPS 下的会话 cookie 已开启 Secure，DERP 使用 WebSocket 以适配反向代理。服务登录正常不等于所有成员所在地网络都已实测，访问异常时先检查 Funnel 状态和网络。

管理员仍可用 `ssh -N -L 127.0.0.1:17080:127.0.0.1:17080 lab-gpu` 转发维护端口；开启 Secure Cookie 后，网页登录统一使用上述 HTTPS 入口，回环 HTTP 供 CLI／健康检查使用。本机独立 Docker 原型的 7080 端口保持原样。

## 网络中转与更新

服务器直连镜像仓库超时后，使用本地网络下载 Linux AMD64 官方镜像；逐层校验摘要后，经 SSH 流式导入指定 rootless Docker。下载与校验记录保存在本地 `.local/remote/`。不改服务器全局镜像源、代理或共享 Docker 配置。

本次机械盘首次历史迁移耗时较长，首轮就绪检查超时；服务继续完成了原生迁移，随后再完成账号与模板初始化。等待期间在本地准备并恢复过一个独立初始库，但切换前检查发现原生迁移已完成，因此未切换使用。未使用的临时库已删除，相关诊断记录在 `.local/remote/`，不复制本地原型的账户或工作区。正常数据库持久化设置始终保留。

provider 准备命令在本地运行：

```bash
conda run --no-capture-output -n lab python scripts/cache_terraform_providers.py --arch amd64 --output .local/remote
```

将其 `provider-mirror/` 和 `provider-manifest.json` 同步到服务器副本的 `.local/`。不要把本机 ARM64 镜像直接复制为服务器镜像。源码由本地同步到服务器副本；同步前检查差异，不覆盖远程已有修改，不同步本机 `.env`、数据库或工作区卷。

## 停止与恢复

先通过 Coder 停止本项目工作区，再执行 Compose `down`。该命令不会删除数据卷，也不会自动停止 Coder 创建的工作区。要停止整个独立 Docker 实例，可运行：

```bash
systemctl --user stop ai4s-docker.service
# 恢复独立 Docker，然后按需启动 Compose 服务及工作区
systemctl --user start ai4s-docker.service
```

不要删除数据目录或使用 `down -v` 作为日常停止操作。系统盘空间不足仍需服务器管理员处理，本项目数据盘部署不等于系统盘问题已解决。

本轮初始化与检查分别通过 `ai4s-bootstrap`、`ai4s-verification` tmux 会话执行，完成后会话自动退出；`.local/bootstrap.log`、`.local/bootstrap.exit`、`.local/verification.log`、`.local/verification.exit` 保存输出和退出状态，`.local/workspace-check.log` 保存 Coder CLI 记录。

验证记录与日志位置见 [环境](environment.md)；实际完成项统一见 [状态](status.md)。实现依据：[Docker rootless 文档](https://docs.docker.com/engine/security/rootless/) 与 [Coder Docker 部署说明](https://coder.com/docs/install/server/docker)。

相关文档：[设计草案](research_plan.md) · [本地操作](local_docker.md) · [CI/CD 接入计划](cicd.md) · [实施计划](implementation_plan.md) · [项目规则](../AGENTS.md) · [仓库入口](../README.md)。
