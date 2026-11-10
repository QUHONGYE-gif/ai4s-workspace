# 当前状态

更新于 2026-11-10。源码能力与已有运行证据如下，尚未部署本轮更新。

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
- 本轮修复通过 10 项独立 AiiDA CPU 集成检查及相关补验；新 Parser 对既有 pk22 产物只读复核通过，未重新执行 GPU。
- 2026-11-08 的快速逻辑检查共 14 项通过，覆盖两次提交上限、清单失效门禁、尝试明细和 A 模块辅助函数；不包含 daemon 或模型执行。
- C 模块 WorkChain 适配层已接入 `allow_reuse`／`force_rerun`／`new_sample` 三种策略、候选映射、实际种子和 `ai4s_decision_records`；Windows 快速逻辑检查均通过，覆盖记录结构、208／209 门禁和三种策略的纯逻辑分支。三种策略的 AiiDA 临时 profile 集成用例已补充，但尚未在本机执行确认。该项尚未合入团队 `aiida-core` fork，不是内核改造完成的证据。

## 限制

- 网页工作流执行、科学产物目录和多人共享仍为模拟；复用决策已在项目 WorkChain 适配层实现，但尚未接入网页／引擎服务。真实 AiiDA 命令行流程尚未接入工作台／Agent API，浏览器命名空间不等于真实成员鉴权。
- 本轮真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口，筛选产物、请求模式和缓存身份的具体限制见模块说明。
- 新增重试、提交核对、复用决策和 daemon 恢复代码尚未在目标 Linux 环境重新运行真实模型或完整集成检查；当前 Windows 开发机只能执行快速逻辑检查，完整 AiiDA daemon 检查在 Windows 跳过。
- 决策扩展点当前位于项目 WorkChain 适配层，尚未合入团队 `aiida-core` fork；跨成员候选查询由站 5／9 提供，网页展示由站 2／10 接入，均不能由本模块单独完成。
- R005 的真实两阶段和仅重筛选记录对应旧源码版本；新版本的尝试日志、失败样例和恢复行为不能由该记录替代。完整缓存身份及跨 profile 共享仍未验收。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

先在目标 Linux AiiDA 环境运行扩展后的 CPU mock 集成检查和一次真实两阶段复验，保留 PK／UUID、尝试状态及 daemon 前后身份；随后由引擎服务透传 `request_id`、`reuse_policy`、候选和 `candidate_results`，由查询接口读取 `ai4s_decision_records`，再接网页的三种策略和理由展示。阶段完成条件仍以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [B 查询](../src/ai4s_query/README.md) · [C 模块](../README_C.md) · [复用决策](reuse_decision.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
