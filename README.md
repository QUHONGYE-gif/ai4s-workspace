# 面向 AI4S 工作流的语义感知数据管理与计算—存储协同工作台

当前工作台业务仍处于初步规划阶段，本地和服务器 Docker + Coder 开发底座已完成初始化。项目内容及设计以以下文档为准；实际进展见状态文件。

代码仓库：[QUHONGYE-gif/ai4s-workspace](https://github.com/QUHONGYE-gif/ai4s-workspace)。本仓库保存可公开的配置、脚本和说明，实际凭据、镜像、provider 缓存和运行数据由各部署环境保管。自动 CI/CD 将在后续接入。

## 文档入口与分工

| 文件 | 阅读目的 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 工作规则、按需阅读和执行约定 |
| [用户原始构想](docs/vision.md) | 查看用户提供的完整原文和本轮要求 |
| [项目设计草案](docs/research_plan.md) | 理解范围、数据对象、复用思路与评价安排 |
| [分阶段实施计划](docs/implementation_plan.md) | 查看接入准备、原型、策略和扩展的任务与完成条件 |
| [当前状态](docs/status.md) | 查看实际完成内容、限制及下一步 |
| [环境与路径](docs/environment.md) | 查看本地原型与服务器配置、环境和执行位置 |
| [本地 Docker 运行说明](docs/local_docker.md) | 启动、使用和停止 Docker + Coder 开发底座 |
| [服务器 Docker 运行说明](docs/server_docker.md) | 数据盘独立 Docker、SSH 隧道与服务器操作 |
| [CI/CD 接入计划](docs/cicd.md) | 后续自动检查与部署的入口、前提和边界 |
| [团队协作约定](docs/collaboration.md) | 个人 Coder 工作区、开发分支及会议后的合并流程 |
| [配置来源](docs/workflow_sources.md) | 维护工作规则时核对来源与配置调整 |
| [蛋白质设计流程跑通记录与使用说明](docs/protein_pipeline.md) | 团队协作主文档一：材料导航、CPU/GPU 分支、实测结果、命令、产物及接手条件 |
| [产物复用与加速协作讨论稿](docs/protein_reuse.md) | 团队协作主文档二：已有缓存、复用条件、证据入口及待共同确认的评测候选 |
| [蛋白质设计试运行 R001](experiments/R001-protein-design-smoke/record.md) | 查看 RFdiffusion → ProteinMPNN → Boltz 的运行身份、命令与中间产物 |
| [Swiss-Prot MSA 试运行 R002](experiments/R002-swissprot-msa/record.md) | 查看 MMseqs2 搜索、A3M、Boltz 对照和设计序列无命中的实际结果 |
| [封装验证 R003](experiments/R003-pipeline/record.md) | 查看真实封装运行、失败修正与备份证据 |
| [MMseqs2 GPU 分支 R004](experiments/R004-mmseqs-gpu/record.md) | 查看 GPU 搜索、MSA、Boltz 分支结果与完整产物记录 |

文档以相对 Markdown 链接相互引用，并提供返回入口。方案、阶段任务、实际状态和运行环境各自维护

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
├── docker/workspace/Dockerfile
├── coder/               # 工作区模板与 Terraform 镜像配置
├── scripts/             # 开发底座与蛋白质设计 pipeline 入口
├── configs/protein_design.matpool.json
├── tests/test_protein_design_pipeline.py
├── experiments/
│   ├── R001-protein-design-smoke/record.md
│   ├── R002-swissprot-msa/record.md
│   ├── R003-pipeline/record.md
│   └── R004-mmseqs-gpu/record.md
└── docs/
    ├── vision.md
    ├── research_plan.md
    ├── implementation_plan.md
    ├── status.md
    ├── environment.md
    ├── protein_pipeline.md
    ├── protein_reuse.md
    ├── local_docker.md
    ├── server_docker.md
    ├── cicd.md
    ├── collaboration.md
    └── workflow_sources.md
```

业务代码与专项研究目录在实际工作需要时建立，约定见 [项目规则](AGENTS.md)。本地开发底座命令见 [运行说明](docs/local_docker.md)。`.gitignore` 排除常见缓存、凭据、数据目录和模型权重；大型产物位置见 [环境说明](docs/environment.md)。
