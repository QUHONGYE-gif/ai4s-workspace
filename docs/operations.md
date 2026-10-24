# 部署与运维

面向管理员。日常应用开发见 [成员协作](collaboration.md)，依赖和环境参数约定见 [运行要求](environment.md)。

## 配置入口

| 入口 | 职责 |
| --- | --- |
| [compose.yaml](../compose.yaml)、[服务器覆盖](../compose.server.yaml)、[HTTPS 覆盖](../compose.https.yaml) | Coder、数据库、网络与持久卷 |
| [开发镜像](../docker/workspace/Dockerfile) | 工作区基础依赖 |
| [个人模板](../coder/templates/server-personal/main.tf)、[启动脚本](../coder/templates/server-personal/startup.sh) | 个人代码卷、初始化和开发预览 |
| [初始化入口](../scripts/init_local_docker.py) | 初始化底座与原型模板 |
| [成员管理](../scripts/configure_members.py) | 开户与发布个人模板 |
| [provider 下载](../scripts/cache_terraform_providers.py)、[Terraform 配置](../coder/terraform.tfrc) | provider 缓存及校验 |
| [部署变量示例](../.env.server.example) | 目标环境需要填写的字段 |

脚本和示例中的地址、账号、路径及架构必须按目标环境核对；初始化和模板发布不是日常启动应用的步骤。

## 成员开户与模板

- 仅为已确认的成员开户。使用 `configure_members.py add`，参数和行为先查看 `--help`；凭据通过团队约定的私有方式交付。
- 模板使用 `publish-template --seed-path <种子目录>` 发布。种子只包含可公开代码，不打包凭据、私有配置或个人未提交内容。
- 发布版本与应用到既有工作区是不同操作；更新前检查影响范围。已有 checkout 不因种子更新自动覆盖。

## 维护与更新

- 先核对目标项目、Docker 实例、配置和正在运行的任务；优先在目标服务器准备匹配平台的镜像和依赖。
- 只更新授权范围内的服务。保留数据库、个人代码卷和运行数据；数据库升级需检查迁移兼容与恢复方法。
- Terraform 管理的资源通过原管理流程变更，不直接删除底层容器造成状态不一致。
- 网络受限时可中转官方依赖，核对平台、版本和摘要，完成后清理无运行依赖的传输缓存。
- 变更后最小验证应用、已有预览及相关数据；按需核对其他成员工作区未被替换或重启。应用启动见 [工作台](../web/README.md) 和 [PyMOL](../tools/pymol_web/README.md)。

## 排错

按故障位置读取应用日志、Coder 工作区状态、代理和 Docker 日志。页面可访问不等于 WebSocket、结构加载或科学任务成功，应验证对应功能。只处理已确认归属的进程；不用删除持久卷、重启 Docker 或全局清理替代诊断。

返回 [仓库入口](../README.md)。
