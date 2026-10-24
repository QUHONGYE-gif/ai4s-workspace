# 运行要求

团队使用 Docker + Coder 的个人工作区。服务器地址、账号、Docker socket、数据目录和资源配额由实际部署配置或管理员提供，不作为共享文档中的固定值。

## 依赖

| 部分 | 要求与配置来源 |
| --- | --- |
| 工作台前后端 | Python 3.10+，运行时仅使用标准库；基础镜像见 [Dockerfile](../docker/workspace/Dockerfile) |
| 前端逻辑检查 | Node.js，仅运行已有测试，页面本身无需构建 |
| PyMOL | 与目标发行版配套的 PyMOL、Qt、Xvfb、noVNC 和 Nginx；[安装与启动](../tools/pymol_web/README.md) |
| 蛋白质设计 | 独立模型环境、权重和数据库，具体字段见 [使用说明](protein_pipeline.md) 与 [配置示例](../configs/protein_design.example.json) |
| Coder 底座 | Compose、Docker 及 Terraform provider；版本以配置和模板锁文件为准 |

## 配置约定

- 部署变量从 [.env.server.example](../.env.server.example) 了解字段，在目标环境填写；已有 `.env` 不用示例覆盖，真实凭据不提交。
- 应用默认使用工作区的 3000 端口，由已有开发预览访问。资源、路由和 WebSocket 使用相对路径，兼容预览前缀。
- Python 服务的数据目录由 `--data-dir` 指定；PyMOL 联合启动器使用用户状态目录。路径和生命周期见各自启动说明。
- 代码和需保留的数据放在已确认的持久化位置；容器系统目录中的依赖可能在重建后丢失。模型、数据库、缓存和运行结果独立保存。

相关文档：[开发入口](../README.md) · [成员协作](collaboration.md) · [部署与运维](operations.md)。
