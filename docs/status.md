# 当前状态

更新于 2026-11-12。源码能力与已有运行证据如下。

## 已具备

- 本人模块的模型身份内核与真实引擎服务已完成 API／原生节点验收；支持单任务、两阶段流程、三种复用策略、同参命中与换权重失效。五份协议正文已通过飞书 CLI 核对；[引擎说明](engine_service.md)维护接口与边界，[R006](../experiments/R006-aiida-engine/record.md)维护真实证据。原共用引擎及个人 profile 保留。

- 工作台演示页面覆盖工作流、实验、候选产物、模拟运行及来源查看；Python API 保存按浏览器命名空间隔离、带修订冲突检查的模拟快照。
- PyMOL 已接入已有工具页面，支持真实 PDB/mmCIF 上传、显示方式切换、网页命令、历史和可折叠输出；简洁视图与完整原生界面共用同一会话。
- 独立蛋白质设计程序提供 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置与执行入口。
- Agent 已嵌入自定义流程接入，支持资料提取、手动／对话改参、端口画布、分支与设计关系、串行配置回填及登记／请求；[运行说明](agent_demo_run.md)。
- 登记流程可交接到实验配置，实验助手共用接入页模型设置；创建后弹出概述，确认后检查候选，再单独启动模拟。支持引用 FASTA 建立仅筛选草稿；[流程与边界](agent_demo_run.md#登记交接与实验配置)。
- 本次实验交接与确认流程通过本地 59 项 Python 检查（另 1 项跳过）、6 个前端测试文件及桌面／移动端浏览器流程验证；助手使用固定测试回复，未进行真实模型或 GPU 验收。
- 复用与存储页面新增独立示例画布；来源、计划与副本整理仅用于交互演示，见 [工作台说明](../web/README.md#复用画布与-aiida-查询快照)。
- B 查询模块已选择性接入，可只读查询原生状态、文件、来源与缓存，并导出工作台离线快照；[接口与限制](../src/ai4s_query/README.md)。
- Docker + Coder 模板及成员管理入口用于个人开发与预览。
- A 模块已提供真实 ProteinMPNN CalcJob／Parser 和独立提交入口，校验运行记录、输入、序列、分数、概率数值及样本对应后发布原生文件 Data 和清单；接口及校验边界见 [A 模块说明](aiida_tasks.md)。
- C 模块提供真实任务编排、上游资格检查与连续重筛选，见 [C 模块说明](../README_C.md)。既有 1CRN 推理、筛选、缓存和下游重算证据见 [R005 记录](../experiments/R005-aiida-proteinmpnn/record.md)。
- A/C 既有修复通过 10 项独立 AiiDA CPU 集成检查及相关补验；Parser 对既有 pk22 产物只读复核通过，未重新执行 GPU。

## 限制

- 原工作台和实验 Agent 仍保留模拟流程；新增真实实验入口经工作台 HTTP 转发到独立引擎。跨成员真实容器查询／复用、全员页面整合与真实成员鉴权尚未完成。
- 既有真实运行仅覆盖 ProteinMPNN 与简单筛选，不覆盖完整 RFdiffusion → ProteinMPNN → Boltz 链路，也不构成性能或科研效果结论。
- A、C 尚未完整实现规划接口，筛选产物、请求模式和缓存身份的具体限制见模块说明。
- R006 用真实 CPU ProteinMPNN 验证身份与策略，未新增 GPU 推理或长任务恢复验收；跨 profile 共享仍未通过，重试与恢复边界见 C 模块说明。
- Agent 为单用户配置原型；新工作区需配置自己的模型 API。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

按任务 4.0 继续对接跨成员候选与数据访问，再将成员登记／实验 Agent 页面接到已验收的真实服务。全员最终验收与 main 合并仍需会议确认；阶段完成条件以 [实施计划](implementation_plan.md) 为准。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [A 模块](aiida_tasks.md) · [B 查询](../src/ai4s_query/README.md) · [C 模块](../README_C.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [仓库](../README.md)。
