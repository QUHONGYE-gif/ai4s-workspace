# 当前状态

更新于 2026-11-15。源码能力与已有运行证据如下。

## 已具备

- `dev-qhy` 已整合 ckz、csr、wyh 最新交付，统一声明、候选 UUID、决策记录和内核。csr 与 qhy 两个真实成员容器的独立 profile 已通过归档传递、两阶段直接复用、单任务原生缓存、强制重算、新采样、不合格排除与换权重验证；完整矩阵及原生核对见 [R007](../experiments/R007-member-reuse/record.md)，版本与接口见 [引擎说明](engine_service.md)。
- 任务注册中心支持版本化声明、逐项编辑、Agent 提案与确认、草稿恢复及导出；规则、发布流程和执行边界集中见 [任务声明](task_declarations.md)。
- [A 模块](aiida_tasks.md)提供真实 ProteinMPNN CalcJob、Parser、原生文件 Data 和产物清单；[C 模块](../README_C.md)支持编排、门禁、受控复用、有限重试与下游重筛选；[B 模块](../src/ai4s_query/README.md)只读查询原生状态、来源、文件、缓存和决策。
- [工作台](../web/README.md)覆盖工作流、实验、候选产物、模拟运行和来源查看；模拟快照按浏览器命名空间隔离并检查修订冲突。[Agent](agent_demo_run.md)支持资料提取、画布编辑、登记交接和实验配置，创建概述确认后再检查候选并启动模拟。
- [PyMOL](../tools/pymol_web/README.md)支持真实结构上传、显示切换和命令会话。[独立蛋白质设计程序](protein_pipeline.md)保留 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置及执行入口。Docker + Coder 用于成员个人开发与预览。
- PR #11 精简了重复声明／决策文档、内核补丁副本、旧三策略验收入口和仅比对文案／副本的断言。业务源码、运行配置和既有实验 JSON 保持不变；历史源码链接保留在相应运行记录中。

- 个人分支接入工作区策略面板，支持手动与 Agent 提案确认、版本历史和撤回。真实实验采用保存的默认复用方式。阈值、预算和保留策略当前用于固定示例验证，见 [工作区策略](engine_service.md#工作区策略) 和 [R008 网页策略验收](../experiments/R008-workspace-policy/record.md)。

## 限制

- 工作台和实验 Agent 保留模拟流程，真实实验经显式入口转发到独立引擎。跨容器共享已验证 csr 与 qhy；其他成员组合、实验 Agent 页面闭环及真实成员鉴权尚未完成。
- 真实运行证据仅覆盖 ProteinMPNN 与简单筛选，未覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，不构成性能或科研效果结论。A、C 的接口限制见各模块说明。
- R006／R007 使用真实 CPU ProteinMPNN；历史 GPU 证据见 [R005](../experiments/R005-aiida-proteinmpnn/record.md)。本轮未新增 GPU 推理、真实模型中断恢复、真实 LLM 或浏览器验收。
- Agent 是单用户配置原型，新工作区需配置模型 API；自动 CI/CD 和正式产品部署尚未接入。

## 下一步

后续按授权范围继续实验 Agent 页面闭环及更多成员组合。PR #11 保持 Draft，不合并 main；合并须经[团队会议](collaboration.md#汇总会议与合并)确认。阶段完成条件以 [实施计划](implementation_plan.md)为准。

返回：[运行要求](environment.md) · [仓库](../README.md)。
