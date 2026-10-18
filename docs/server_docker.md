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

## 访问

在本机运行 SSH 隧道并保持连接：

```bash
ssh -N -L 127.0.0.1:17080:127.0.0.1:17080 lab-gpu
```

本轮已建立该隧道，控制 socket 在本地 `.local/remote/coder-tunnel.sock`；如需关闭本轮隧道，在本地仓库运行 `ssh -S .local/remote/coder-tunnel.sock -O exit lab-gpu`。后续重新访问可使用上面的普通前台隧道命令。

然后访问 `http://localhost:17080`。该地址区别于本机 Docker 原型的 7080 端口。服务只绑定服务器回环地址；具有服务器 SSH 权限的协作者可建立各自隧道。当前提供管理员原型工作区，尚未配置团队账户及独立代码 checkout；多人接入遵循 [团队协作约定](collaboration.md)。

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
