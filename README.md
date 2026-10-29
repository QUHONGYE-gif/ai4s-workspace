# AI4S 工作台

面向科学中间产物的身份、依赖、共享与复用，首个场景为蛋白质设计。

当前包含工作台演示前后端、独立蛋白质设计程序及嵌入式 PyMOL。工作流执行、产物目录和复用策略仍为模拟；真实 PyMOL 结构查看已接入。能力边界见 [当前状态](docs/status.md)。

## 开发入口

- [工作台前后端](web/README.md)：文件职责、启动、API 与已有测试。
- [PyMOL](tools/pymol_web/README.md)：在已有工作区启动结构查看、网页命令和完整界面。
- [蛋白质设计](docs/protein_pipeline.md)：配置、运行与输出约定。
- [实验记录与复用讨论](docs/protein_reuse.md)：个人分支保留的 R001–R004 证据及讨论材料。
- [成员协作](docs/collaboration.md)：个人工作区、预览与 PR 合并。

- [AI 辅助生成](docs/agent_demo_run.md)：在“接入自定义流程”内使用 DeepSeek 对话、配置模型参数并回填接入草稿。

## 文档分工

| 文档 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 开发、执行与验证规则 |
| [原始构想](docs/vision.md) | 用户提出的研究目标 |
| [设计草案](docs/research_plan.md) | 产物、依赖、复用含义及评价思路 |
| [实施计划](docs/implementation_plan.md) | 后续阶段与完成条件 |
| [当前状态](docs/status.md) | 当前能力、限制与下一步 |
| [运行要求](docs/environment.md) | 通用依赖和配置来源 |
| [部署与运维](docs/operations.md) | 管理员操作入口及维护边界 |

## 代码位置

- `web/demo/`：页面、交互、API 客户端与嵌入式查看器。
- `src/workbench/`：HTTP API、模拟快照和 PyMOL 接口。
- `scripts/`：应用、蛋白质流程和管理入口。
- `tools/pymol_web/`：PyMOL 启动与路径代理。
- `configs/`、`coder/`、`docker/`、`compose*.yaml`：配置、模板与镜像定义。
- `tests/`：已有的输入边界、状态接口及前端逻辑检查。

凭据、模型、数据库、缓存和运行产物不提交到 Git。个人环境参数由实际部署配置提供。
