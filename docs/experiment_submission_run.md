# 实验提交与结果展示（开发任务 4.0 · 站 2、10）

面向验收的说明与记录。范围是任务书里邹佳轩负责的两站：**站 2 实验提交**、**站 10 结果与来源页**，外加**实验页 Agent** 与开发期用的**模拟引擎**。

## 0　实现状态（11-12 晚）

| 项 | 状态 |
| --- | --- |
| 模拟引擎（约定②④⑤） | 完成，已自测并通过工作台转发 |
| 引擎接入开关（off/mock/real） | 完成，默认 off，不静默假成功 |
| 实验页 Agent 右栏、移除接入入口、运行前摘要确认、Agent 运行指令 | 完成 |
| 说明文档 | 本文件 |
| **页面提交真实任务（调用 `/api/engine/*`）** | **未完成**：页面当前仍走本地模拟草稿，接口契约与模拟服务已就绪 |
| **结果与来源页接查询接口** | **未完成**：仍展示本地模拟的 plan/outputs |
| MOCK/REAL 角标与"演示数据"水印 | 后端已提供 `engine.mode/base`，前端展示未做 |


## 1　目标与边界

任务原文：让网页提交真实任务，并看到运行状态、产物、来源和复用理由；实验页 Agent 围绕当前实验回答。

- 本轮实现页面与接口调用链；**真实引擎由曲鸿烨提供**，未交付前用按约定②⑤搭的模拟服务自测。
- 科学执行、AiiDA 过程、指纹计算均不在网页侧实现；网页只提交请求、轮询状态、展示返回结构。
- 页面不自行推断复用结论：`decision.action`、`cached_from`、候选与理由全部来自引擎响应。

## 2　实验提交页（站 2）

| 要求 | 实现 |
| --- | --- |
| 按约定①生成参数表单 | 参数定义来自 `configs/task_declarations/proteinmpnn/1.json`；推理参数与筛选参数分开渲染（`category=inference/filter`），必填、默认值、枚举、范围按声明校验 |
| 三种复用选择 | 「允许复用 / 强制重算 / 新采样」以 `reuse_policy`（`allow_reuse` / `force_rerun` / `new_sample`）提交，符合约定② |
| 提交与状态 | 前端调用 `/api/engine/uploads` → `/api/engine/requests`，随后每 3 秒轮询 `/api/engine/requests/{id}`，状态按约定②的 `accepted → submitted → running → finished / failed` 显示 |
| 失败原因 | 直接展示 `error.code` 与 `error.message`（`invalid_params` / `input_not_found` / `engine_unavailable` 等） |

### 交互调整（按 11-12 反馈）

1. 实验页 Agent 面板从左侧工作流下方移到**右栏**，排在「实验范围与策略」之前；面板内不再提供 Agent 接入入口（接入与密钥只在「智能体接入」页）。
2. 「创建前摘要」不再固定显示在页面上，改为**运行时确认**：点「创建实验」或由 Agent 发起运行时弹出摘要（输入、请求步骤、参数覆盖、缺失项），确认后才提交。
3. Agent 可自主运行：用户说「直接跑一次 / 自动跑完」时返回 `run_experiment`，前端弹摘要 → 用户确认 → 自动创建实验并启动，无需再点「创建实验 / 确认运行」。已创建实验的快照只读，不允许再次运行。

## 3　结果与来源页（站 10）

| 要求 | 实现 |
| --- | --- |
| 展示产物 | 读 `outputs.result`、`outputs.artifacts.*`（sequences / scores / probabilities）与两阶段的 `selected_sequences`、`selection_report` |
| 来源链路 | 展示 `process.uuid`、`cached_from`（复用时指向被复用过程）、`effective.identity_digest` 与 `fingerprint`（约定③字段） |
| 复用还是重跑、为什么 | 读 `decision.action` / `reason_code`，并按 `request_id` 取约定⑤决策记录：候选比较列表、最终决定、理由文字、时间 |
| 数据实时读取 | 状态与结果来自引擎响应的轮询结果，不再依赖本页手工导入的快照 |

> 数据来源标注：页面显示当前引擎模式（`off / mock / real`）与 base URL，mock 模式下的结果一律标注「演示数据，非真实计算」。

## 4　模拟引擎（开发期替代）

`scripts/mock_engine.py` 按约定②实现四个接口，并按约定④⑤产出候选与决策记录：

```bash
# 只跑模拟引擎
python scripts/mock_engine.py --port 3010

# 工作台 + 模拟引擎（页面显示 MOCK）
python scripts/serve_workbench.py --port 3000 --engine-mode mock

# 接真实引擎（拿到地址后）
python scripts/serve_workbench.py --port 3000 --engine-mode real --engine-base http://<host>:<port>

# 联合模式（工作台 + Agent + 模拟引擎）
uv run python scripts/run_agent_demo.py --with-workbench --port 3000 --engine-mode mock
```

覆盖范围：五个状态；三种 `reuse_policy`（R01 复用 / R02 无合格候选降级重算 / R03 强制重算 / R04 新采样换种子）；提交前参数校验（种子为 0、温度非正、序列数不整除 `batch_size`、`single` 流程带筛选参数等）。

**限制（必须在验收时说明）**：模拟引擎不计算指纹、不写 AiiDA 节点、不做真实质检；它只能证明页面闭环与状态机，不能作为"复用命中 / 指纹 / 决策记录"的验收证据。

## 5　验证记录

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 前端逻辑 | `node tests/test_demo_logic.cjs` | 21 项通过（含 Agent 面板位置、摘要不再内联、无草稿禁止 `run_experiment`） |
| 工作台 API | `python -m unittest tests/test_workbench_api.py` | 9 项通过 |
| 模拟引擎 | 上传 → 提交 → 轮询 | 五状态推进；`allow_reuse` 首次 R02、同参数再次 R01 且 `cached_from` 有值；`force_rerun` R03；`new_sample` R04 且种子 41→42；非法参数返回 `failed/invalid_params` |
| 转发链路 | 经工作台访问 `/api/engine/*` | `health` 200；`single` 与 `mpnn_filter` 均 202 并进入 finished |

## 6　验收演示脚本（3 分钟）

1. 打开预览 → 根路径是项目介绍页 → 进入工作台 → 实验页。
2. 确认右上角引擎标识：`MOCK`（或 `REAL <base>`）。
3. 填参数：设计链 A、序列数 4、温度 0.1、种子 41；选「允许复用」→ 创建 → 摘要确认 → 观察 accepted/submitted/running/finished。
4. 同参数再提交一次 → 决策应显示 `reuse` 且来源指向上一过程（`cached_from`）。
5. 选「强制重算」→ 决策 `rerun`；选「新采样」→ `effective.seed` 变化。
6. 打开结果与来源：产物、过程 UUID、决策理由文字。
7. 对 Agent 说："直接按现在的参数跑一次" → 弹摘要 → 确认 → 自动创建并运行；再说"这次为什么没有重算" → Agent 依据决策记录回答。

## 7　未完成与待接

- **真实引擎地址未交付**：拿到 base URL 后按上面命令切 `real`，页面无需改动。
- **查询接口（站 9）路径未定**：现用 `/api/engine/requests/{id}/decisions` 与 `/candidates`，属提案；对接时集中改一处适配层。
- 页面的 MOCK/REAL 角标与"演示数据"水印已具备数据（`/api/health.engine`），视觉部分待补。
- 结果页的产物文件预览仍为占位，真实文件需按 `outputs.artifacts` 取回后再实现。
