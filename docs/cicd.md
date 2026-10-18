# CI/CD 接入计划

用户已明确后续加入自动 CI/CD 部署。本文件记录接入建议及现有入口；当前没有启用 GitHub Actions 工作流，也没有配置自动部署凭据。实际运行状态见 [状态](status.md)，手动操作见 [服务器说明](server_docker.md)。

## 配置与产物分工

| 内容 | 当前来源与后续用途 |
| --- | --- |
| 服务定义 | [基础 Compose](../compose.yaml)、[服务器覆盖配置](../compose.server.yaml) 与 [HTTPS 入口覆盖配置](../compose.funnel.yaml)，由 Git 版本管理；入口运维见 [服务器说明](server_docker.md) |
| 工作区镜像 | [Dockerfile](../docker/workspace/Dockerfile)，服务器构建目标为 `linux/amd64`、`USER_UID=1000` |
| 工作区模板 | [原型模板](../coder/templates/local-docker/main.tf) 与 [个人模板](../coder/templates/server-personal/main.tf) 及各自锁文件，更新模板是独立步骤 |
| 服务器变量 | [.env.server.example](../.env.server.example) 描述字段，真实 `.env` 留在服务器，不能用示例覆盖 |
| provider 缓存 | [下载脚本](../scripts/cache_terraform_providers.py) 按版本、架构下载并校验，服务启动前准备到 `.local/provider-mirror/` |
| 运行数据 | 数据库、Coder home、工作区 home 和共享卷留在独立 Docker 中；不随代码发布替换 |

Git 不存储登录密码、会话 token、SSH 密钥、镜像导出文件、缓存及运行日志。现有验证记录保存在部署机器的 `.local/`，不随公开仓库分发。以后若 CI 产生报告，仅发布移除凭据后的检查摘要。

## 建议分两步接入

1. **CI：先检查与构建。** 对提交和 PR 检查 Python／Shell 语法、文档链接、Compose 配置；使用示例环境变量，运行 `docker compose --env-file .env.server.example -f compose.yaml -f compose.server.yaml config --quiet`，不要输出展开后的真实配置。随后构建 AMD64 工作区镜像并记录 commit 与镜像 digest 的对应关系。业务实现后再加入相应测试。
2. **CD：再连接服务器。** 共享部署以按照 [团队协作约定](collaboration.md) 经会议通过并合入 `main` 的版本为来源，个人开发分支不触发共享部署。选择能通过 SSH 或本机执行访问服务器的 runner；按项目规则只操作独立 rootless Docker。同一环境的部署串行执行。实际 SSH 凭据、主机校验信息及必要发布凭据由后续部署配置提供，不写入仓库。

当前 `lab-gpu` 是本机 SSH 别名，不能假定 GitHub runner 已配置该别名或能访问服务器。runner 的位置、镜像发布位置和自动部署触发条件在接入时再确定。

## 后续部署顺序与现有入口

以下是拟定顺序，不是已经实现的自动发布脚本：

1. 记录目标 commit，核对服务器代码副本是否有本地修改或正在使用的工作区。当前工作区直接挂载该副本，更新文件会立即影响使用者；自动覆盖之前需要确定发布窗口或独立代码副本方案。
2. 准备目标 AMD64 镜像和 provider 包，网络不通时按 [中转说明](server_docker.md#网络中转与更新) 经本地传输。现有开发镜像仅存于部署环境；后续应发布可追溯的版本标签／digest，并同步调整初始化脚本和模板变量中的镜像引用。
3. 在服务器保留现有 `.env` 和数据卷，明确工作目录及 Docker socket，检查配置后应用 Compose：

   ```bash
   cd /data1/qhy/projects/ai4s-workbench/repo
   export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
   docker compose -f compose.yaml -f compose.server.yaml -f compose.funnel.yaml config --quiet
   docker compose -f compose.yaml -f compose.server.yaml -f compose.funnel.yaml up -d --wait --wait-timeout 180
   docker compose -f compose.yaml -f compose.server.yaml -f compose.funnel.yaml ps
   curl --fail --silent --show-error --max-time 15 http://127.0.0.1:17080/api/v2/buildinfo
   ```

4. 需要更新模板时单独处理。现有 [初始化入口](../scripts/init_local_docker.py) `--server --skip-build` 会登录管理员并推送模板，适用于初始化／手动更新；接入 CD 时再拆出独立模板发布步骤及认证。仅更新 Compose 不会更新已经运行的 Coder 工作区镜像。
   个人模板使用 [成员说明](members.md#管理员准备种子与发布模板) 中的独立发布命令，并保留旧原型模板私有权限；不要将个人代码卷替换成共享部署目录。
5. 保存 commit、镜像 digest、执行时间及健康检查结果。初次数据库迁移可能超过等待上限，先查日志与迁移状态，不把超时直接视为数据库损坏或触发重建。

[集成验证脚本](../scripts/check_local_docker.py) 会停止和重启 `prototype`，应在专用验证工作区或明确的检查窗口执行，不能直接作为每次部署的在线健康探针。现有完整验证结果见状态文件。

服务配置更新前保留旧版本及所需镜像；涉及 Coder／数据库升级时先备份数据库并检查迁移兼容性。代码回退不能撤销数据库迁移，不能用删除卷、清空数据目录或系统 Docker 清理来实现回滚。

相关文档：[服务器运行说明](server_docker.md) · [本地运行说明](local_docker.md) · [环境与路径](environment.md) · [当前状态](status.md) · [仓库入口](../README.md)。
