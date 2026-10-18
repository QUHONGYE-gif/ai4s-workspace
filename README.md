# 面向 AI4S 工作流的语义感知数据管理与计算—存储协同工作台

本项目探索科学中间结果的身份、依赖与复用，先以蛋白质生成工作流验证。Docker + Coder 开发底座已建立，日常开发使用服务器个人工作区；工作台业务和科学流程仍处于规划阶段。实际进展以 [当前状态](docs/status.md) 为准。

代码仓库：[QUHONGYE-gif/ai4s-workspace](https://github.com/QUHONGYE-gif/ai4s-workspace)。本仓库保存可公开的代码、配置和说明；凭据、运行数据、镜像与缓存留在对应环境。

## 从哪里开始

- 成员登录、开发、预览、提交 PR：[成员开发与协作](docs/collaboration.md)。
- 管理员部署、开户、更新模板和排错：[部署与运维](docs/operations.md)。
- 了解研究方向和下一步：[设计草案](docs/research_plan.md) → [实施计划](docs/implementation_plan.md) → [当前状态](docs/status.md)。

## 核心文档分工

| 文件 | 唯一维护内容 |
| --- | --- |
| [项目规则](AGENTS.md) | Agent 工作方式、按需阅读、科研与执行边界 |
| [用户原文](docs/vision.md) | 用户构想和明确要求的原始表述 |
| [设计草案](docs/research_plan.md) | 范围、科学数据对象、复用含义和评价思路 |
| [实施计划](docs/implementation_plan.md) | 阶段任务、产物、完成条件及后续 CI/CD 计划 |
| [当前状态](docs/status.md) | 已完成内容、验证证据索引、限制和最近下一步 |
| [环境说明](docs/environment.md) | 机器、版本、路径、持久卷、资源限额和中转位置 |
| [成员开发与协作](docs/collaboration.md) | 成员使用、个人开发预览、分支与会议合并流程 |
| [部署与运维](docs/operations.md) | 管理员部署、开户、种子与模板、HTTPS、排错和本地恢复操作 |
| [配置来源](docs/workflow_sources.md) | 工作规则的参考来源与职责调整记录 |

方案、计划、状态、环境和操作分别维护，通过相对链接引用；成员指南与管理员运维入口分开。

## 当前文件结构

```text
.
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── .env.server.example
├── .github/pull_request_template.md
├── compose.yaml
├── compose.server.yaml
├── compose.https.yaml
├── docker/workspace/Dockerfile
├── coder/               # 原型与个人工作区模板、Terraform 配置及锁文件
├── configs/             # HTTPS 中转、SSH 限制与服务配置
├── scripts/             # 初始化、成员管理、provider 下载及辅助入口
└── docs/
    ├── vision.md
    ├── research_plan.md
    ├── implementation_plan.md
    ├── status.md
    ├── environment.md
    ├── collaboration.md
    ├── operations.md
    └── workflow_sources.md
```

业务代码、专项研究和实验目录按实际需要建立，约定见 [项目规则](AGENTS.md)。配置文件及可执行入口索引见 [运维文档](docs/operations.md#配置入口)；大型产物和环境位置见 [环境说明](docs/environment.md)。`.gitignore` 排除凭据、缓存、数据目录和模型权重。
