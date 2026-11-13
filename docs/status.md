# 当前状态

更新于 2026-11-13。源码能力与已有运行证据如下，尚未部署本轮更新。

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
- 2026-11-13 在 Coder 的独立 AiiDA fork 环境与临时 profile 上执行主项目集成检查，15 项 CPU mock 测试全部通过（Ran 15 tests，OK）；覆盖三种复用策略、实际种子与启动次数、决策记录查询、daemon 停止／重启恢复、重试成功与上限、无效清单及复用 schema 门禁。
- 2026-11-13 fork 内核的 `tests/engine/test_reuse.py` 使用 ZeroMQ 后端运行 15 项测试，全部通过；覆盖受控复用决策、候选结果消费、原生缓存边界和用户策略约束。默认 RabbitMQ 后端未配置，因此该组测试必须使用 `--broker-backend=zmq`。
- 2026-11-13 在 Coder 独立 profile `ai4s-wyh-reuse` 上完成 fork 接入后的真实 GPU 同一请求三策略复验：`request_id=req-f433676d-d4b0-429b-8b44-cb8a21813678`，WorkChain PK 7／24／33 分别为 `force_rerun`／`allow_reuse`／`new_sample`，决策记录分别为 R03／R01／R04，共 3 条。`force_rerun` 使用种子 41 创建 CalcJob PK 8；`allow_reuse` 复用 CalcJob PK 8 的结果且不创建 CalcJob；`new_sample` 使用种子 `883420096` 创建 CalcJob PK 34。三项 WorkChain 均为 `Finished [0]`，脚本状态为 `passed`。证据见 [same-request-f433676d.json](../experiments/R005-aiida-proteinmpnn/same-request-f433676d.json)。
- 2026-11-11 在授权 GPU 环境完成三种复用策略的真实复验：`force_rerun` WorkChain PK 74 使用原种子 41 启动 CalcJob PK 75；`allow_reuse` WorkChain PK 94 复用真实结果节点 `87ada36e-8a31-4805-b5f8-52813d27219f` 且未创建 CalcJob；`new_sample` WorkChain PK 107 改用种子 `3491716553` 并启动 CalcJob PK 109。三次 WorkChain 均为 `Finished [0]`，没有 CalcJob 缓存来源，`ai4s_decision_records` 可按各自 `request_id` 查回 R03／R01／R04。该次真实 GPU 运行早于 fork 内核接入，不能替代接入后的真实复验。详见 [R005 记录](../experiments/R005-aiida-proteinmpnn/record.md)。
- 2026-11-08 的快速逻辑检查共 14 项通过，覆盖两次提交上限、清单失效门禁、尝试明细和 A 模块辅助函数；不包含 daemon 或模型执行。
- C 模块已通过 `get_reuse_configuration()` 将 `request_id`、`reuse_policy`、候选和决策函数提交给 fork 内核；`reuse` 使用 `ReuseMaterialization.CONSUME_CANDIDATE` 注入已有候选，`rerun`／`new_sample` 禁止回退到 AiiDA 原生整进程缓存。对应 fork 为 `WuYuhui01/aiida-core` 的 `dev-wyh` 分支、提交 `9a1e474f2`。

## 限制

- 网页工作流执行、科学产物目录和多人共享仍为模拟；复用决策已接入 AiiDA fork 内核并通过隔离集成测试，但尚未接入网页／引擎服务。真实 AiiDA 命令行流程尚未接入工作台／Agent API，浏览器命名空间不等于真实成员鉴权。
- 本轮真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口，筛选产物、请求模式和缓存身份的具体限制见模块说明。
- 三种复用策略的真实 GPU 链路已在 2026-11-11 的项目适配层验证，并于 2026-11-13 在 fork 接入后的独立 profile `ai4s-wyh-reuse` 上完成同一 `request_id` 复验。`allow_reuse` 使用同一 profile 内的真实结果候选，不等同于跨成员／跨 profile 共享。真实 daemon 中断恢复仍主要依赖 Linux CPU mock；网页尚未实时回显 AiiDA 决策记录。
- fork 内核目前只在独立环境和临时 profile 中验证，尚未部署到共享 profile；跨成员候选查询由站 5／9 提供，网页展示由站 2／10 接入，均不能由本模块单独完成。
- R005 的真实两阶段和仅重筛选记录对应旧源码版本；新版本的尝试日志、失败样例和恢复行为不能由该记录替代。完整缓存身份及跨 profile 共享仍未验收。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

下一步由引擎服务透传 `request_id`、`reuse_policy`、`reuse_candidates`、`candidate_results`，由查询接口读取 `ai4s_decision_records`，最后接入网页展示；同时继续验证真实 daemon 中断恢复和跨成员共享。网页实时回显、真实 daemon 中断恢复以及跨成员共享仍是后续联调范围。阶段完成条件仍以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [B 查询](../src/ai4s_query/README.md) · [C 模块](../README_C.md) · [复用决策](reuse_decision.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
