# 当前状态

## 已具备

- 工作台演示页面覆盖工作流、实验、候选产物、模拟运行及来源查看；Python API 保存按浏览器命名空间隔离、带修订冲突检查的模拟快照。
- PyMOL 已接入已有工具页面，支持真实 PDB/mmCIF 上传、显示方式切换、网页命令、历史和可折叠输出；简洁视图与完整原生界面共用同一会话。
- 独立蛋白质设计程序提供 RFdiffusion → ProteinMPNN → 可选 MMseqs2 → Boltz-2 的配置与执行入口。
- Docker + Coder 模板及成员管理入口用于个人开发与预览。

- 个人分支保留 R001–R004 的真实租用 GPU 实验记录及证据；历史 CPU 搜索封装与独立 GPU 搜索分支已实跑。现有重构版本与历史执行快照分别判断，见 [流程记录](protein_pipeline.md)。

- Agent 接入 Demo 已实现三模型参数配置、资料识别、真实 DeepSeek 工具调用、登记与请求生成；本机历史 API 验收见 [运行记录](agent_demo_run.md)。已接入工作台导航与相对路径预览，并同步到个人 Coder；目标环境 37 项 Python 检查、浏览器改参与刷新持久化通过。Coder 的 DeepSeek 密钥尚未配置，本次未在该环境重跑真实 API 验收，详见运行说明。

## 限制

- 工作流执行、科学产物目录、多人共享和复用策略仍为模拟；浏览器命名空间不等于真实成员鉴权。
- 蛋白质程序尚未与工作台 API 联通，当前版本没有目标环境端到端 GPU 验收或科研效果结论。
- 自动 CI/CD 与正式产品部署尚未接入。

## 下一步

按 [实施计划](implementation_plan.md) 接通工作台与一条小规模真实蛋白质链路，参考已有 [R001–R004 记录](protein_pipeline.md)，登记产物与依赖，再验证查询和复用。

入口：[工作台](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [蛋白质设计](protein_pipeline.md) · [仓库](../README.md)。
