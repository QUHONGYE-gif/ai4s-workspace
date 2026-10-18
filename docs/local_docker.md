# 本地 Docker + Coder 运行说明

本文件维护启动、使用、停止和检查操作。实际版本、路径和部署状态分别见 [环境说明](environment.md) 与 [当前状态](status.md)；开发底座在项目中的作用见 [设计草案](research_plan.md)。

## 配置入口

- [compose.yaml](../compose.yaml)：Coder 控制面、专用 PostgreSQL、项目网络与持久卷。
- [开发镜像](../docker/workspace/Dockerfile)：Python、Git、curl 和普通用户。
- [工作区模板](../coder/templates/local-docker/main.tf)：独立用户目录、仓库挂载及共享数据卷。
- [Terraform 镜像配置](../coder/terraform.tfrc)与[下载入口](../scripts/cache_terraform_providers.py)：校验官方 Linux ARM64 provider 包，在本项目 `.local/provider-mirror/` 缓存，供模板安装使用。
- [初始化脚本](../scripts/init_local_docker.py)：构建镜像、启动服务、初始化本地管理员并导入模板。
- [验证脚本](../scripts/check_local_docker.py)：创建或使用本项目的 `prototype` 工作区，执行连接、读写和停止／启动持久化检查。
- [.env.example](../.env.example)：配置示例。实际密码保存在 Git 忽略的 `.env`，初始用户名和邮箱对应 `CODER_BOOTSTRAP_USERNAME`、`CODER_BOOTSTRAP_EMAIL`，密码对应 `CODER_BOOTSTRAP_PASSWORD`。

## 初始化与日常启动

在仓库根目录运行，Docker Desktop 须已启动：

```bash
conda run --no-capture-output -n lab python scripts/init_local_docker.py
```

脚本保留已有 `.env` 和数据库，自动生成本地密码时将文件权限设为 600，并准备本项目的 provider 缓存。首次执行需要配置中指定的官方镜像可用；若拉取通道失败，可使用本机网络下载、验证后加载镜像，不修改全局 Docker 或代理配置。代理字段仅使用当前机器已有、且容器可访问的服务。

日常启动和检查不必重新构建或导入模板：

```bash
docker compose up -d --wait
docker compose ps
docker compose logs --tail 50 coder
```

访问地址从环境文档读取。初始本地管理员可以修改自己的资料和密码；修改后不要用旧的初始化密码重复执行需要登录的初始化步骤。

## 工作区使用

本轮已创建原型工作区，名称见环境文档。也可以在 Coder 选择 `local-docker` 模板创建新的工作区。通过内置网页终端进入 `/workspace/project`；本轮先提供终端开发入口，浏览器 IDE 可按后续需求接入。

每个工作区的 `/home/coder` 独立持久化；`/workspace/project` 是当前本地仓库的实时挂载；`/shared` 是本原型的共享数据卷。停止／重启工作区后，用户目录和共享数据保留。

当前仓库挂载用于本机原型调试。多人正式共同开发按 [团队协作约定](collaboration.md) 使用个人分支和独立 checkout；共享产物放共享数据位置。Coder 的工作区创建与共享卷只提供基础环境，本项目的产物语义、有效性判断和复用策略仍需实现。

## 停止与持久化

先在 Coder 停止工作区，再停止控制面：

```bash
docker compose down
```

Coder 管理的工作区不属于 Compose 服务，单独停止控制面不会自动停止工作区。普通 `down` 保留数据库与控制面数据卷；日常停止不附加删除卷的选项。

## 本次检查

验证入口：

```bash
conda run --no-capture-output -n lab python scripts/check_local_docker.py
```

该检查会停止并重新启动本项目的 `prototype` 工作区，执行时不在其中同时开展其他任务。检查只写入自己创建的临时标记，成功后清理。

实际结果在 [状态](status.md) 维护；`.local/initialization.json` 保存时间、工作区身份、检查项和源码哈希，`.local/bootstrap.log`、`.local/workspace-check.log` 保存初始化与检查输出，`.local/provider-manifest.json` 保存 provider 校验信息。首次 provider 网络失败日志保存在 `.local/bootstrap-network-failure.log`。这些是开发底座验证，后续蛋白质任务见 [实施计划](implementation_plan.md)。

Terraform provider 镜像使用 [官方 filesystem mirror 配置](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation)，缓存只包含当前 Linux ARM64 平台。迁移到其他架构时需下载对应包。

实现参考：[Coder 官方 Docker 部署示例](https://github.com/coder/coder/blob/release/2.38/compose.yaml)、[Docker 工作区模板](https://github.com/coder/coder/blob/v2.38.0/examples/templates/docker/main.tf)。官方 Docker 部署文档面向 Linux；本配置是针对本机 Docker Desktop Linux VM 的本地适配，其可用性以实际检查为准，参见 [安装说明](https://coder.com/docs/install/server/docker)。

相关文档：[服务器操作](server_docker.md) · [环境](environment.md) · [状态](status.md) · [实施计划](implementation_plan.md) · [项目规则](../AGENTS.md) · [仓库入口](../README.md)。
