# 当前状态

更新于 2026-11-05，依据 PR #9 的实现和 qhy 个人 AiiDA profile 中的已有节点回查。模块实现、命令行验证与网页接入分别记录。

## 已具备

- 工作台演示页面覆盖工作流、实验、候选产物、模拟运行及来源查看；Python API 保存按浏览器命名空间隔离、带修订冲突检查的模拟快照。
- PyMOL 已接入已有工具页面，支持真实 PDB/mmCIF 上传、显示方式切换、网页命令、历史和可折叠输出；简洁视图与完整原生界面共用同一会话。
- 独立蛋白质设计程序提供 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置与执行入口。
- Agent 已嵌入自定义流程接入，支持资料提取、手动／对话改参、端口画布、分支与设计关系、串行配置回填及登记／请求；[运行说明](agent_demo_run.md)。
- 实验创建先保存为待运行状态，确认候选后启动模拟；流程图支持配置／结果切换、按需节点详情和产物来源入口。
- Docker + Coder 模板及成员管理入口用于个人开发与预览。
- A 模块已提供真实 ProteinMPNN CalcJob／Parser 和独立提交入口，校验运行记录、输入、序列、分数及概率形状后发布原生文件 Data 和清单；接口及校验边界见 [A 模块说明](aiida_tasks.md)。
- C 模块已接入真实任务，完成真实 1CRN → 4 条设计序列与分数 → 筛选，以及复用同一上游 Data 的仅重筛选；保留 mock、有限重试和独立临时 profile 检查，见 [C 模块说明](../README_C.md)。
- 已回查单任务成功、单任务缓存命中、真实两阶段成功及下游重算的原生 UUID、参数、结果和链接；详细身份、命令与结果见 [R005 运行记录](../experiments/R005-aiida-proteinmpnn/record.md)。

## 限制

- 网页工作流执行、科学产物目录、多人共享和复用策略仍为模拟；真实 AiiDA 命令行流程尚未接入工作台／Agent API，浏览器命名空间不等于真实成员鉴权。
- 本轮真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口：筛选目前读取清单内联样本、输出 Dict；通用任务声明、统一请求模式、完整计算身份与缓存失效规则尚未完成。具体差异分别维护在模块说明中。
- daemon 停启恢复、真实 WorkChain 内缓存命中、B 对本次产物的来源反查、多人共享及跨 profile 访问尚未验收。有限重试实际允许三次提交，与本轮两次尝试的口径待对齐。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

先对齐 A、C 的产物门禁、公共端口和重试次数；接入 B 查询本次真实节点，补齐故障、缓存身份与 daemon 恢复验收，再将任务准备、提交和查询连接到现有 Agent／工作台。阶段完成条件仍以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [C 模块](../README_C.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
