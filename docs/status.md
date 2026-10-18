# 当前状态

更新时间：2026-10-18（Asia/Shanghai）。

## 已完成

- 项目原文、设计草案和阶段计划已整理；文档职责与双向导航已建立，三个本地技能已移除，服务器段落沿用参考项目。
- 本地 Docker + Coder 开发底座已初始化，控制面、专用数据库和原型工作区保持运行。实际版本、访问地址和数据位置统一见 [环境说明](environment.md)，命令见 [本地运行说明](local_docker.md)。
- 已验证登录 API、Coder SSH、仓库读写、用户目录与共享卷写入；停止并启动工作区后文件仍保留，检查临时文件已清理。
- 模板及 provider 版本已固定；本地 provider 镜像已按官方注册表 SHA-256 校验。初始化入口可重复执行并保留已有账户和数据；详细证据见 `.local/initialization.json` 及运行说明中的日志索引。

## 服务器部署（已完成）

- 已在数据盘配置独立 rootless Docker，镜像、容器和持久卷均使用该实例；统一资源限额和具体路径见 [环境说明](environment.md)。已有共享 Docker 容器保持运行。
- 已完成服务器 Coder、数据库、管理员、工作区模板和原型工作区初始化。现通过 HTTPS 入口访问，操作见 [服务器运行说明](server_docker.md)。
- 登录 API、Coder SSH、仓库读写、home／共享卷写入以及停止／启动后持久化全部通过；工作区保持运行，探针临时文件已清理。
- 服务器镜像和 provider 经本地网络中转；首次数据库迁移因机械盘同步开销而超出首轮等待时间，随后原生迁移完成。备用初始库未切换使用，已删除。
- 远程 `.local/initialization.json` 记录集成检查，本地 `.local/remote/` 保存回传证据、镜像来源和部署源码快照。没有科研实验或 GPU 运行结果。

## 浏览器直连入口（服务端已部署，公网 DNS 待生效）

- 用户已认领 Tailscale 设备，并明确批准 Funnel 承载 Coder 登录、API、网页终端及开发流量。实际 HTTPS 网址和操作统一见 [服务器运行说明](server_docker.md#访问)。目标为成员无需 SSH 隧道或 Tailscale 客户端，公网可用性仍待下述验证。
- 已经本地中转、官方 SHA-256 校验，将 Tailscale `1.104.1` AMD64 安装到数据盘；独立 userspace 用户服务已启动，属于现有项目资源限额。Funnel 持久代理 Coder 回环端口，HTTPS 覆盖配置已生效，个人模板保持 Docker 内部 agent 连接。
- 已通过 HTTPS 验证四位成员登录、Secure Cookie、工作区在线及跨成员访问拒绝；WebSocket 终端在 `qhy/dev` 成功执行命令并确认个人分支。仅重建了 Coder 控制面，四个成员工作区、管理员原型和数据库的容器身份均未改变。证据保存在本地 `.local/remote/public-access/verification.json` 及远程 `.local/public-access/containers-after.json`。
- 本机已接入 Tailscale，前述检查走现有网络，不能作为公网 Funnel 验证。首次开启超过约 10 分钟后，Google／Cloudflare 公共 DNS 仍无该域名记录，服务器普通 DNS 也无法解析；已核对 Funnel 能力、HTTPS 权限、持久配置及 `Hostinfo.IngressEnabled=true` 上报，并重载专用接入服务。当前公网发布阻塞，需记录生效后执行非 tailnet 验证，也未进行各成员所在地网络及多人并发评测。入口依赖 Tailscale Funnel 中继和带宽限制；当前用于开发交互，大型科研数据在服务器内部处理。

## 成员与代码隔离

- 已发布 `server-personal` 模板及普通成员开户入口；个人代码和 Git 状态使用独立持久卷，首次启动进入个人分支。旧原型模板已改为管理员私有。操作与范围见 [成员说明](members.md)。
- 两个临时普通成员实测通过：登录和自建工作区、跨成员访问拒绝、分支及文件隔离、独立卷挂载、重启后保留未提交修改；另已确认普通成员无法访问旧原型模板。测试账号、工作区及卷已清理，管理员原型保持运行。远程 `.local/member-isolation-check.json` 与 `.local/member-template-permission-check.json` 保存证据，本地副本在 `.local/remote/`。
- 已按用户确认的名单创建 `csr`、`zjx`、`qhy`、`ckz` 四个普通成员账号；各自 `dev` 工作区已运行，使用独立代码卷及对应 `dev-首字母` 分支，GitHub 同名分支均已存在。四人登录、本人工作区访问、跨成员访问拒绝和旧模板访问拒绝均已验证，管理员原型保持运行。
- 账号邮箱及独立初始密码只保存在本地 `.local/members/`，未发送邮件或代配成员 GitHub 凭据、协作者权限；工作区和访问检查记录在 `.local/remote/member-onboarding*.json` 与 `.local/remote/named-members-verification.json`。

## 当前限制

- 用户已确认 [团队协作约定](collaboration.md)，已记录个人工作区、分支及会议后合并流程，并补充 PR 模板。协作规则、成员配置及四人成员接入记录 PR 已在仓库端合并；本轮 HTTPS 入口变更经 `dev-qhy` 提交待审 PR，不直接写入 `main`。2026-10-18 查询时 GitHub `main` 分支保护尚未启用；文档约定不等于平台强制执行。

- 已实现范围为开发底座；科学产物目录、复用策略、工作台业务网页和模型接入尚未实施，无科研效果结论。
- 本地原型与服务器各有一个管理员及原型工作区；正式成员已开户，尚未进行真实多人协作业务评测。
- 蛋白质工具版本、输入样例和可用后端未核查；当前工作区是 CPU 开发环境，GPU 容器接入尚未配置。
- GitHub 仓库保存配置、脚本和文档；服务器凭据、运行数据及私有验证记录不纳入版本管理。已补充 [CI/CD 接入计划](cicd.md) 和服务器配置示例，自动检查与部署尚未启用。

## 最近下一步

在现有开发底座上，按 [实施计划](implementation_plan.md) 先选择最小的蛋白质步骤与产物，随后实现业务原型。后续阶段不由本地初始化自动启动。

相关文档：[用户原文](vision.md) · [设计草案](research_plan.md) · [项目规则](../AGENTS.md) · [仓库入口](../README.md)。
