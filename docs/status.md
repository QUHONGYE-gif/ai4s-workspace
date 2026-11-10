# 当前状态

更新于 2026-11-10。源码能力与已有运行证据如下；个人 Coder 开发预览不代表团队正式部署。

## 已具备

- 工作台演示页面覆盖工作流、实验、候选产物、模拟运行及来源查看；Python API 保存按浏览器命名空间隔离、带修订冲突检查的模拟快照。
- PyMOL 已接入已有工具页面，支持真实 PDB/mmCIF 上传、显示方式切换、网页命令、历史和可折叠输出；简洁视图与完整原生界面共用同一会话。
- 独立蛋白质设计程序提供 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置与执行入口。
- Agent 已嵌入自定义流程接入，支持资料提取、手动／对话改参、端口画布、分支与设计关系、串行配置回填及登记／请求；[运行说明](agent_demo_run.md)。
- ProteinMPNN 约定①登记支持真实接口定义、手动／Agent 提案、确认写入与校验导出；提供共享文件加载器，实际引擎加载与②提交尚待联调，见 [声明登记与交付](task_declaration_run.md)。
- 实验创建先保存为待运行状态，确认候选后启动模拟；流程图支持配置／结果切换、按需节点详情和产物来源入口。
- 复用与存储页面新增独立示例画布；来源、计划与副本整理仅用于交互演示，见 [工作台说明](../web/README.md#复用画布与-aiida-查询快照)。
- B 查询模块已选择性接入，可只读查询原生状态、文件、来源与缓存，并导出工作台离线快照；[接口与限制](../src/ai4s_query/README.md)。
- 个人分支保留 R001–R004 的真实租用 GPU 实验记录及证据，见 [蛋白质流程记录](protein_pipeline.md)。
- Docker + Coder 模板及成员管理入口用于个人开发与预览。
- A 模块已提供真实 ProteinMPNN CalcJob／Parser 和独立提交入口，校验运行记录、输入、序列、分数、概率数值及样本对应后发布原生文件 Data 和清单；接口及校验边界见 [A 模块说明](aiida_tasks.md)。
- C 模块提供真实任务编排、上游资格检查与连续重筛选，见 [C 模块说明](../README_C.md)。既有 1CRN 推理、筛选、缓存和下游重算证据见 [R005 记录](../experiments/R005-aiida-proteinmpnn/record.md)。
- 本轮修复通过 10 项独立 AiiDA CPU 集成检查及相关补验；新 Parser 对既有 pk22 产物只读复核通过，未重新执行 GPU。

## 限制

- 网页工作流执行、科学产物目录、多人共享和复用策略仍为模拟；真实 AiiDA 命令行流程尚未接入工作台／Agent API，浏览器命名空间不等于真实成员鉴权。
- 本轮真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口，筛选产物、请求模式和缓存身份的具体限制见模块说明。
- 新版本的真实模型失败／重试、完整缓存身份、daemon 恢复及跨 profile 共享尚未完整验收；重试次数口径见 C 模块说明。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

先对齐公共端口和重试次数，补齐故障、缓存身份与 daemon 恢复验收，再将任务准备、提交和查询连接到现有 Agent／工作台。阶段完成条件仍以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [B 查询](../src/ai4s_query/README.md) · [C 模块](../README_C.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
