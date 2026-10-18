# 部署与运维

本文件面向管理员，统一维护服务器部署、成员开户、模板发布、HTTPS 接入和本地原型恢复。日常开发见 [成员开发与协作](collaboration.md)；机器、版本、路径和资源上限见 [环境说明](environment.md)，实际进展与验收证据见 [当前状态](status.md)。下列命令只在相应操作需要时执行，不是每次登录的启动清单。

导航：[配置入口](#配置入口) · [服务器部署](#服务器部署) · [维护与更新](#服务器维护与更新) · [成员开户](#成员开户) · [种子与模板](#种子与模板维护) · [HTTPS](#https-接入) · [排错与回退](#入口排错与回退) · [本地恢复](#本地原型恢复) · [验证与日志](#验证与日志)。

## 配置入口

| 文件 | 唯一维护内容 |
| --- | --- |
| [基础 Compose](../compose.yaml) | Coder、专用 PostgreSQL、网络和持久卷 |
| [服务器覆盖配置](../compose.server.yaml) | 独立项目名、socket、用户和 CPU 限额 |
| [HTTPS 覆盖配置](../compose.https.yaml) | 对外 URL、Secure Cookie、DERP WebSocket |
| [开发镜像](../docker/workspace/Dockerfile) | Python、Git、curl 和用户；服务器目标 `linux/amd64`、构建参数 `USER_UID=1000` |
| [原型模板](../coder/templates/local-docker/main.tf) | 本地／服务器原型的仓库挂载、网络与工作区变量 |
| [个人模板](../coder/templates/server-personal/main.tf) | 独立代码卷、只读种子、初始化脚本和开发预览；各模板锁文件固定 provider |
| [本地变量示例](../.env.example)／[服务器变量示例](../.env.server.example) | 配置字段；真实 `.env` 不入 Git，不用示例覆盖已有文件 |
| [Terraform 配置](../coder/terraform.tfrc)／[下载脚本](../scripts/cache_terraform_providers.py) | 按版本和架构下载、校验并使用 provider 缓存 |
| [Nginx 配置](../configs/nginx-coder.conf) | 独立 HTTPS 虚拟主机、ACME 路径与 WebSocket 转发 |
| [SSH 限制](../configs/ai4s-tunnel-sshd.conf)／[通道服务](../configs/ai4s-coder-relay.service) | 专用账号仅向中转机回环端口转发、固定主机公钥、自动重连 |
| [续期钩子](../configs/ai4s-certbot-reload.sh) | 校验并平滑 reload Nginx |

Git 只保存可公开的代码和配置；密码、令牌、SSH 密钥、镜像包、缓存和运行数据留在对应环境，不能随发布替换数据库或成员卷。

## 服务器部署

本项目复用已有 rootless Docker 组件，在数据盘使用独立实例；不为共享 `/var/lib/docker` 建软链接，也不迁移、重启或清理共享 Docker。[启动脚本](../scripts/start_server_docker.sh) 保留已有服务声明，利用用户 linger 在 SSH 登出后运行。容器 `0:0` 映射为宿主机用户 `qhy`，不是宿主机 root；GPU 接入另按 [项目规则](../AGENTS.md) 核实。

在科研服务器明确选择工作目录与 socket，禁止用未指定目标的清理命令：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
docker info --format '{{.DockerRootDir}}'
systemctl --user status ai4s-docker.service
```

仅首次创建独立实例时执行 `sh scripts/start_server_docker.sh`；该脚本针对当前用户、rootless 组件和 systemd 环境，换机器前须核对环境。已有部署沿用原 `.env`；首次生成时使用排他创建，密码不输出到终端：

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

准备好服务器架构的镜像和 provider 后执行：

```bash
python3 scripts/init_local_docker.py --server --skip-build
```

`--skip-build` 要求已经导入服务器开发镜像，版本见环境说明。脚本保留已有账号与数据库，登录管理员并发布原型模板；个人模板使用下文独立流程。注册表同名标签的可拉取性不能由本地已核验标签保证，新环境须先准备并核验镜像。

## 服务器维护与更新

服务器网络失败时，可在本地下载 Linux AMD64 官方镜像，校验摘要后经 SSH 导入指定 rootless Docker；不改服务器全局镜像源、代理或共享 Docker。provider 在本地准备：

```bash
conda run --no-capture-output -n lab python scripts/cache_terraform_providers.py --arch amd64 --output .local/remote
```

将产出的 `provider-mirror/` 与 `provider-manifest.json` 同步到服务器副本 `.local/`。不要将本机 ARM64 镜像冒充服务器镜像。源码同步前检查差异，保护远程修改和正在使用的管理员原型挂载；正式成员使用独立 checkout。只同步必要文件，不同步本机 `.env`、数据库、成员卷或大型数据。

更新前记录目标 commit、保留旧配置和所需镜像。Coder／数据库升级须先备份数据库并检查迁移兼容性；代码回退不能撤销数据库迁移。明确进入服务器项目目录，使用三个 Compose 文件：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
docker compose -f compose.yaml -f compose.server.yaml -f compose.https.yaml config --quiet
# 仅更新控制面；成员连接可能短暂断开，数据库及工作区不随此命令重建
docker compose -f compose.yaml -f compose.server.yaml -f compose.https.yaml up -d --no-deps coder
docker compose -f compose.yaml -f compose.server.yaml -f compose.https.yaml ps
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:17080/api/v2/buildinfo
```

只有明确需要应用整个 Compose 栈时，才将上述 `up` 行改为 `up -d --wait --wait-timeout 180`。保存 commit、镜像 digest、执行时间和健康检查结果；数据库首次迁移可能超过等待上限，先查日志，不因超时直接重建数据库。自动化仍属于 [后续 CI/CD 计划](implementation_plan.md#后续-cicd)。

停止时先通过 Coder 停止相应工作区，再以同一组 Compose 文件执行 `down`；它保留卷，但不会自动停止 Coder 创建的工作区。停用整个独立实例使用 `systemctl --user stop ai4s-docker.service`，恢复使用 `systemctl --user start ai4s-docker.service`，再按需启动 Compose 服务与工作区。不把 `down -v`、删除数据目录或清理共享 Docker 用作停止／回退。数据盘部署不表示系统盘空间问题已经解决。

## 成员开户

只按用户确认的身份开户。取得三字小写首字母和邮箱后，在服务器项目目录执行；显示名称可暂用首字母，真实姓名由成员自行补充：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
python3 scripts/configure_members.py add \
  --initials abc --name 'abc' --email 'member@example.com'
```

也可在本地建立 [管理员维护隧道](#入口排错与回退)，在 `add` 前加入 `--env-file .local/remote/.env`；不要向成员分发管理员配置。

[开户脚本](../scripts/configure_members.py) 创建普通成员，随机密码仅写入执行机器的 `.local/members/abc.json`，权限 `600`，终端只输出路径。管理员单独交付该成员密码；登录邮箱和凭据不发布到公开仓库，也不发送未获授权的邮件。

同名同邮箱已存在时保留原密码和角色；同名不同邮箱时停止并协调冲突。中断后留下 `pending` 记录时，先查实际创建结果，不覆盖记录或自动重置密码。开户本身不创建 GitHub 协作者权限或代配成员凭据；工作区分配和首次使用见 [成员指南](collaboration.md#登录与个人工作区)。

## 种子与模板维护

种子从公开 GitHub 仓库生成，不能对含私有配置或未公开提交的本地工作目录直接打包。种子目录与个人卷位置见 [环境说明](environment.md#个人工作区)。首次在本地准备：

```bash
git clone --mirror https://github.com/QUHONGYE-gif/ai4s-workspace.git .local/remote/member-seed.git
git -C .local/remote/member-seed.git bundle create ../repository.bundle --all
git -C .local/remote/member-seed.git bundle verify ../repository.bundle
```

已有镜像仓库先执行 `git -C .local/remote/member-seed.git fetch --prune origin`，再生成新 bundle。经 SSH 传至服务器临时文件，验证后原子替换种子 `repository.bundle`。只影响后来创建的 checkout，不覆盖已有个人代码。

将个人模板目录（含 `main.tf`、`startup.sh`、锁文件）及开户脚本同步到服务器后，执行：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
python3 scripts/configure_members.py publish-template \
  --seed-path /data1/qhy/projects/ai4s-workbench/member-seed
```

该命令发布 `server-personal`，并通过 `templates edit server-docker --private --yes` 保持旧原型模板私有。当前详细模板 ACL 接口属于 Premium 功能，私有模板开关可用；不要向普通成员开放挂载部署目录的原型模板。

发布模板或更新 Compose 不会自动更新已运行的成员工作区。当前 Coder 版本在工作区重新构建时会更换 Agent 令牌，可能重建容器；先检查成员任务、端口、可写层、持久卷及代码状态，再逐个更新并核对登录、预览权限和代码摘要。保留已有 checkout，不重新克隆、切分支或 reset。新成员直接获得当前模板；管理员原型继续使用旧模板。

## HTTPS 接入

连接路径和两端配置位置统一见 [环境说明](environment.md#https-中转位置)。服务器 `.env` 中 `AI4S_PUBLIC_URL` 应与当前 HTTPS 入口一致；原始端口只监听回环，数据库和 Docker socket 不对外发布。

部署前确认目标文件不存在或与仓库一致，已有不同配置先核对，不整份覆盖 Nginx、SSH 或 `.env`。专用账号与公钥按环境说明中的限制配置后，运行 `sshd -t` 并平滑 reload SSH；科研服务器用户服务先以 `systemd-analyze --user verify` 检查，再 `daemon-reload` 和 `enable --now ai4s-coder-relay.service`。

首次签发证书时，先建立仅含 HTTP ACME location 的独立虚拟主机，确认公网挑战文件可读，再在云服务器执行：

```bash
certbot certonly --non-interactive --webroot -w /var/lib/ai4s-coder/acme \
  --cert-name coder.my-rustdesk.xyz -d coder.my-rustdesk.xyz --keep-until-expiring
```

证书存在后安装完整 Nginx 配置，执行 `nginx -t && systemctl reload nginx`，保留原网站；续期沿用既有 timer 和项目 reload 钩子。切换入口只调整 Coder `.env` 的 `AI4S_PUBLIC_URL`，再按 [控制面更新步骤](#服务器维护与更新) 应用。

## 入口排错与回退

管理员需要回环维护接口时，在本机执行：

```bash
ssh -N -L 127.0.0.1:17080:127.0.0.1:17080 lab-gpu
```

网页登录仍走 HTTPS，回环 HTTP 用于 CLI 和健康检查。依次检查 Coder、服务器间通道、Nginx 与证书，不将登录页 200 或服务 active 当作完整验收：

```bash
# 科研服务器
cd /data1/qhy/projects/ai4s-workbench/repo
systemctl --user status ai4s-coder-relay.service
journalctl --user -u ai4s-coder-relay.service -n 30 --no-pager
curl -fsS http://127.0.0.1:17080/healthz

# 阿里云中转机
ss -lnt | grep 27080
curl -fsS http://127.0.0.1:27080/healthz
nginx -t
systemctl status certbot.timer
```

完整公网验收包括真实证书、成员登录、Secure Cookie、本人工作区与开发预览、跨成员／匿名拒绝及 WebSocket 网页终端查询个人分支。日志路径见环境说明；基线和验收索引见状态。

恢复独立 Nginx／SSH 通道配置时保留当前 `AI4S_PUBLIC_URL`；只有修改 Coder 环境配置才重建控制面。撤下本项目入口时，仅移除本项目 Nginx 启用链接，`nginx -t` 后平滑 reload，再停止科研服务器通道服务。保留原网站、数据库、成员卷及 SSH 管理账号；仅停用时保留通道密钥与配置用于恢复。

## 本地原型恢复

日常开发以服务器为主，本地原型已停用，清理结果见状态；本节用于按需恢复，未在本次文档整理中执行。确认 Docker Desktop 已启动，使用 `desktop-linux`，保留原 `.env` 和命名卷，不用服务器配置覆盖本地文件。

按 [本地环境版本](environment.md#已有本地原型) 准备 Linux ARM64 基础镜像，数据库使用与原数据卷兼容的 PostgreSQL 17。已移除镜像的身份在 `.local/local-docker-retirement/removed-image-identities.json`；下载后核验并使标签与 `.env`、Compose、Dockerfile 对齐，再运行：

```bash
DOCKER_CONTEXT=desktop-linux conda run --no-capture-output -n lab python scripts/init_local_docker.py
```

脚本保留已有 `.env` 和数据库，初次生成凭据时设为 `600`，准备 provider 缓存并构建开发镜像。下载失败时可用本机现有网络中转，不修改全局代理；配置中的代理须从容器可达。宿主机 Conda 不挂入容器。

登录原本地账号，在 Coder 启动已有 `prototype`，无需重新开户。home／共享数据从保留卷恢复，`/workspace/project` 仍实时挂载本地仓库。管理员若已改密码，不要继续用旧初始化密码运行需要登录的脚本。

镜像准备好后的日常启动、检查与停止：

```bash
docker --context desktop-linux compose up -d --wait
docker --context desktop-linux compose ps
docker --context desktop-linux compose logs --tail 50 coder
# 先在 Coder 停止工作区，再停止控制面；不附加 -v
docker --context desktop-linux compose down
```

## 验证与日志

[集成检查](../scripts/check_local_docker.py) 会创建或使用 `prototype`，执行登录、Coder SSH、读写以及实际停止／启动后的持久化检查；仅写入并清理临时标记。检查期间不要在原型中运行其他任务，也不要把该脚本当作每次部署的在线健康探针：

```bash
# 科研服务器项目目录，已显式指定本项目 DOCKER_HOST
python3 scripts/check_local_docker.py --server
# 本地仓库，按需恢复后才运行
DOCKER_CONTEXT=desktop-linux conda run --no-capture-output -n lab python scripts/check_local_docker.py
```

本地 `.local/initialization.json` 记录时间、工作区、检查项和源码哈希，`.local/bootstrap.log`、`.local/workspace-check.log` 保存输出，`.local/provider-manifest.json` 保存 provider 摘要，首次网络失败另存 `.local/bootstrap-network-failure.log`。服务器对应 `.local/` 还保存 `bootstrap.exit`、`verification.log`、`verification.exit`；历史 `ai4s-bootstrap`、`ai4s-verification` tmux 会话完成后已退出。回传路径见环境说明，各轮结果和私有证据索引只在状态文件维护。这些检查不代表蛋白质工作流或科研效果已验证。

依据：[Docker rootless](https://docs.docker.com/engine/security/rootless/) · [Coder Docker 部署](https://coder.com/docs/install/server/docker) · [固定版本 Compose](https://github.com/coder/coder/blob/release/2.38/compose.yaml) · [原型模板参考](https://github.com/coder/coder/blob/v2.38.0/examples/templates/docker/main.tf) · [Terraform filesystem mirror](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation) · [Coder 用户 API](https://coder.com/docs/reference/api/users) · [启动脚本资源](https://registry.terraform.io/providers/coder/coder/2.19.0/docs/resources/script) · [Coder Nginx](https://coder.com/docs/tutorials/reverse-proxy-nginx) · [OpenSSH 转发](https://man.openbsd.org/ssh#R)。本地配置是 Docker Desktop Linux VM 适配，实际验证范围见状态。

相关文档：[成员开发与协作](collaboration.md) · [环境](environment.md) · [状态](status.md) · [实施计划](implementation_plan.md) · [项目规则](../AGENTS.md) · [仓库入口](../README.md)。
