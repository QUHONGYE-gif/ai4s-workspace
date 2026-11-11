# 当前状态

更新于 2026-11-11。源码能力与已有运行证据如下，尚未部署本轮更新。

## 已具备

- 工作台演示页面覆盖工作流、实验、候选产物、模拟运行及来源查看；Python API 保存按浏览器命名空间隔离、带修订冲突检查的模拟快照。
- PyMOL 已接入已有工具页面，支持真实 PDB/mmCIF 上传、显示方式切换、网页命令、历史和可折叠输出；简洁视图与完整原生界面共用同一会话。
- 独立蛋白质设计程序提供 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置与执行入口。
- Agent 已嵌入自定义流程接入，支持资料提取、手动／对话改参、端口画布、分支与设计关系、串行配置回填及登记／请求；[运行说明](agent_demo_run.md)。
- 实验创建先保存为待运行状态，确认候选后启动模拟；流程图支持配置／结果切换、按需节点详情和产物来源入口。
- 复用与存储页面新增独立示例画布；来源、计划与副本整理仅用于交互演示，见 [工作台说明](../web/README.md#复用画布与-aiida-查询快照)。
- B 查询模块已选择性接入，可只读查询原生状态、文件、来源与缓存，并导出工作台离线快照；[接口与限制](../src/ai4s_query/README.md)。
- Docker + Coder 模板及成员管理入口用于个人开发与预览。
- A 模块已提供真实 ProteinMPNN CalcJob／Parser 和独立提交入口，校验运行记录、输入、序列、分数、概率数值及样本对应后发布原生文件 Data 和清单；接口及校验边界见 [A 模块说明](aiida_tasks.md)。
- C 模块提供两阶段 WorkChain、最多两次提交、逐次尝试身份／状态／启动计数、已知失效清单门禁、稳定 label 提交核对、daemon 恢复检查入口和连续重筛选，见 [C 模块说明](../README_C.md)。既有 1CRN 推理、筛选、缓存和下游重算证据见 [R005 记录](../experiments/R005-aiida-proteinmpnn/record.md)。
- 2026-11-11 在 Linux 开发环境的 AiiDA 2.9.4 临时 profile 上执行完整 15 项 CPU mock 集成检查，全部通过；覆盖三种复用策略、实际种子与启动次数、决策记录查询、daemon 停止／重启恢复、重试成功与上限、无效清单及复用 schema 门禁。
- 2026-11-11 在授权 GPU 环境完成真实单任务和 `force_rerun` 两阶段 WorkChain 复验：单任务 PK 60、WorkChain PK 74／UUID `89fea7d1-1fdd-41c8-904d-788b674ab888`、实际 CalcJob PK 75 均为 `Finished [0]` 且无缓存来源；实际种子为 41，`model_launches=1`、`attempt_count=1`，筛选得到 2 条结果，`ai4s_decision_records` 可按 `request_id` 查回 R03 记录。详见 [R005 记录](../experiments/R005-aiida-proteinmpnn/record.md)。
- 2026-11-08 的快速逻辑检查共 14 项通过，覆盖两次提交上限、清单失效门禁、尝试明细和 A 模块辅助函数；不包含 daemon 或模型执行。
- C 模块 WorkChain 适配层已接入 `allow_reuse`／`force_rerun`／`new_sample` 三种策略、候选映射、实际种子和 `ai4s_decision_records`；Windows 快速逻辑检查均通过，Linux CPU mock 集成检查也验证了三种策略的端到端行为。该项仍位于项目 WorkChain 适配层，尚未合入团队 `aiida-core` fork，不是内核改造完成的证据。

## 限制

- 网页工作流执行、科学产物目录和多人共享仍为模拟；复用决策已在项目 WorkChain 适配层实现，但尚未接入网页／引擎服务。真实 AiiDA 命令行流程尚未接入工作台／Agent API，浏览器命名空间不等于真实成员鉴权。
- 本轮真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口，筛选产物、请求模式和缓存身份的具体限制见模块说明。
- 真实的 `force_rerun` 两阶段链路已经验证；`allow_reuse`、`new_sample`、daemon 中断恢复和决策记录查询仍主要依赖 Linux CPU mock。网页尚未实时回显 AiiDA 决策记录，Windows 快速检查仍只覆盖逻辑。
- 决策扩展点当前位于项目 WorkChain 适配层，尚未合入团队 `aiida-core` fork；跨成员候选查询由站 5／9 提供，网页展示由站 2／10 接入，均不能由本模块单独完成。
- R005 的真实两阶段和仅重筛选记录对应旧源码版本；新版本的尝试日志、失败样例和恢复行为不能由该记录替代。完整缓存身份及跨 profile 共享仍未验收。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

下一步由引擎服务透传 `request_id`、`reuse_policy`、`reuse_candidates`、`candidate_results`，由查询接口读取 `ai4s_decision_records`，再接入网页的三种策略和理由展示。真实 GPU 的单任务和 `force_rerun` 两阶段复验已完成；`allow_reuse`／`new_sample` 的真实候选复用与网页实时回显仍待联调。阶段完成条件仍以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [B 查询](../src/ai4s_query/README.md) · [C 模块](../README_C.md) · [复用决策](reuse_decision.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
