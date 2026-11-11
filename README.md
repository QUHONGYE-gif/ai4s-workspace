# AI4S 工作台

面向科学中间产物的身份、依赖、共享与复用，首个场景为蛋白质设计。

当前包含工作台演示前后端、独立蛋白质设计程序及嵌入式 PyMOL。工作流执行、产物目录和复用策略仍为模拟；真实 PyMOL 结构查看已接入。能力边界见 [当前状态](docs/status.md)。

## 开发入口

- [工作台前后端](web/README.md)：文件职责、启动、API 与已有测试。
- [PyMOL](tools/pymol_web/README.md)：在已有工作区启动结构查看、网页命令和完整界面。
- [蛋白质设计](docs/protein_pipeline.md)：配置、运行与输出约定。
- [成员协作](docs/collaboration.md)：个人工作区、预览与 PR 合并。

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
| [存储层原型说明](src/storage/README.md) | 运行复用验证原型，查看命令行与数据落地位置 |
| [查询模块说明](src/ai4s_query/README.md) | AiiDA 运行结果与来源查询：状态、血缘、产物校验与复用区分 |
| [跨成员候选查找与查询接口](docs/task4-candidates-and-query-api.md) | 任务 4.0 站 5/9：约定④ 候选列表、共享方式选型、只读查询服务与真实运行记录 |

## 代码位置

- `web/demo/`：页面、交互、API 客户端与嵌入式查看器。
- `src/workbench/`：HTTP API、模拟快照和 PyMOL 接口。
- `src/ai4s_query/`：AiiDA 运行结果与来源查询模块（只读），入口 `python -m ai4s_query.cli`。
- `scripts/`：应用、蛋白质流程和管理入口。
- `tools/pymol_web/`：PyMOL 启动与路径代理。
- `configs/`、`coder/`、`docker/`、`compose*.yaml`：配置、模板与镜像定义。
- `tests/`：已有的输入边界、状态接口及前端逻辑检查。

凭据、模型、数据库、缓存和运行产物不提交到 Git。个人环境参数由实际部署配置提供。

Agent 资料与对话配置接入见 [运行说明](docs/agent_demo_run.md)；继续使用已有工作台与 PyMOL 联合启动入口。

`src/storage/` 为后端存储层验证原型（内容寻址对象存储 + SQLite 元数据），说明见 [存储层原型说明](src/storage/README.md)。

`src/ai4s_query/` 为 AiiDA 运行结果与来源查询模块：给定节点 UUID 输出状态、输入参数、产物与校验记录、血缘与缺失信息，区分缓存命中与直接复用，说明见 [查询模块说明](src/ai4s_query/README.md)。
