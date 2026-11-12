# ProteinMPNN 任务声明登记与交付

本页面完成约定①的声明编辑、真实 Agent 提案、用户确认和 JSON 导出。声明规则以 [约定①](task_declaration_contract.md) 为准，完整声明文件为 [proteinmpnn/1.json](../configs/task_declarations/proteinmpnn/1.json)。当前支持真实任务接口的 `single` 和 `mpnn_filter` 定义；导出不等于引擎已登记，也不等于实验已提交。

## 使用入口

沿用 [Agent 工作流接入的启动方式](agent_demo_run.md#安装和启动)，在工作台选择 **工作流 → 接入自定义流程 → AI 辅助生成 → ProteinMPNN 任务登记 · 约定①**。原有三模型图编辑器在同一入口的“流程配置演示”中保留，数据独立，不将旧 Demo 字段直接当作真实 AiiDA 参数。

页面先展示“输入 → ProteinMPNN → 输出”接口图，另列可选的推理后筛选。节点与下方“输入／参数／输出”详情联动；参数逐项展开，JSON、版本与执行映射收在“高级”中。图展示已保存的接口定义，不表示任务运行或文件已生成。AI 助手通过页首按钮按需展开。界面交互参考 [Dify 的节点面板与折叠字段](https://github.com/langgenius/dify/tree/main/web/app/components/workflow/nodes)及 [React Flow 的端口节点](https://github.com/xyflow/xyflow/tree/main/examples/react/src/examples/CustomNode)，沿用现有网页实现，无新增图编辑框架。

1. 在“草稿操作”中新建空白声明，或从完整的已核实定义新建。草稿保存在现有 Agent 服务的数据目录 `declaration_drafts/`，不写入发布目录。
2. 页面展示输入、推理／筛选参数、必填性、真实默认值、范围、输出及所属阶段。展开“试填联调参数”可编辑示例；示例值与后端默认值分开。
3. 手动修改后点击“预览修改”；也可粘贴／读取文本资料，向登记助手说明修改要求。真实 DeepSeek 调用需要先在页面配置 API；密钥仅存服务端，不包含在声明、公开响应及 Git 中。
4. 助手只生成提案。查看目标字段、旧值、新值和来源后，“确认并写入”整批保存；取消不改变已保存声明。普通问答不修改声明。缺项可保留为草稿，但不能导出；非法值和接口冲突整批拒绝，不部分保存。
5. 页首“校验并导出”下载 `<version>.json`。缺项、类型错误、虚构默认值、不支持的端口／执行映射都会阻止导出。已发布版本内容不可覆盖，自定义内容需使用新接口版本；这不意味着新版本已经获团队批准。
6. 把通过审核的文件交给发布负责人，纳入 `configs/task_declarations/<task_id>/<version>.json` 并部署。完整责任与加载规则见 [约定①](task_declaration_contract.md)第9节。

本轮只接受已核实 ProteinMPNN 接口。资料可用于解释、补齐和填写合法示例；不能仅凭 Agent 改写科学参数语义或支持新模型。恢复定义只补缺项，保留已经编辑的名称、说明和示例。已有表单编辑须先确认或显式读取保存版本，再发送对话，避免两种编辑互相覆盖。

## 实现与引擎交接

| 内容 | 入口 | 边界 |
| --- | --- | --- |
| 版本化声明文件 | `configs/task_declarations/proteinmpnn/1.json` | 普通 JSON，无密钥、服务器路径或任意命令 |
| 共用校验／文件加载器 | `src/ai4s_declarations/registry.py` | 标准库，不依赖 AiiDA；验证全部文件后才可用，非法 JSON、重复字段、路径／版本不一致会阻止加载 |
| 草稿与确认 API | `src/ai4s_demo/declarations.py` | 单用户、单进程 JSON 存储；修订冲突与重复确认保护；不提供发布注册接口 |
| 真实模型助手 | `src/ai4s_demo/declaration_agent.py` | PydanticAI + 现有 DeepSeek 网关，独立审核修改意图，后端校验后只生成提案 |
| 登记页面 | `src/ai4s_demo/web/declaration.js` | 在现有工作台中挂载；前后端均沿用路径前缀 |

引擎组可以复用加载器：

```python
from ai4s_declarations import DeclarationRegistry

registry = DeclarationRegistry("configs/task_declarations")
declaration = registry.get("proteinmpnn", "1")
# 未登记的引用抛出 KeyError("invalid_declaration")，由引擎按约定②映射响应。
```

当前网页服务在启动时加载声明，但**实际 AiiDA 引擎服务尚未接入此加载器**。引擎组仍需完成声明引用解析、真实输入引用检查、模型身份③、构造 builder、状态／结果查询和④⑤的联调。不能把网页草稿 API 当作约定②提交接口；它们操作不同对象。

接口清单：

- `GET /api/task-declarations`、`GET /api/task-declarations/{task_id}/{version}`：已加载定义。
- `GET/POST /api/declaration-drafts`、`GET /api/declaration-drafts/{id}`：编辑草稿。
- `POST .../{id}/preview`、`POST .../{id}/messages`：生成手动／Agent 提案，不写入声明内容。
- `POST .../{id}/confirm`、`POST .../{id}/cancel`：按提案编号明确确认／取消；确认接口只使用服务端保存的候选内容。
- `POST .../{id}/export`：完整校验后返回声明、内容 SHA-256 与交付路径，状态为 `exported_not_deployed`。

除新建外，修改、消息和导出请求都带 `expected_revision` 与 `operation_id`。生产环境仍需成员鉴权、权限及多进程存储；当前沿用个人 Coder 工作区的单用户原型，不扩大现有部署边界。

## 验证记录

自动化验证命令：

```bash
uv run pytest -q
node --test tests/*.cjs
```

本次本地回归为 **63项 Python 测试、5个 JavaScript 测试文件全部通过**。已验证既有测试及新增声明测试：完整定义与协议附录一致，拒绝非法种子／类型／整除关系／未知字段，缺项阻止导出；预览不写入、取消不写入、确认只写一次、旧修订拒绝；同版本发布不可变、恢复缺项保留用户修改、非法 Agent 批次不部分保存、旧流程数据保持独立。模型替身测试仅验证程序机制，不作为真实 LLM 证据。

另外将推理规则与 `source_reference.revision` 指定的 A 模块源码逐字核对：14组合法／非法参数用例和3个真实后端默认值一致。筛选规则保持有限阈值、正整数 top_k，不增加0～1范围或生成条数上限。此项是接口一致性检查，不是模型效果评估。

2026-11-10，在个人 Coder 工作区实际运行网页服务，使用服务端已有 `deepseek-flash` 配置完成下列验收。浏览器经 Coder CLI 的本地端口转发连接同一工作区服务；没有复制密钥到浏览器或测试脚本。

| 验收 | 实际结果 |
| --- | --- |
| 真实 Agent 补齐缺失定义 | 2次模型请求、6.28秒；生成18项输入／参数／输出差异，确认前仍为 r0，点击确认后为 r1且无缺项；没有改变名称、版本或示例 |
| 浏览器拒绝非法示例 | 手动填写 seed=0 后返回422；不打开确认弹窗，仍为 r1 |
| 浏览器下载 | `1.json` 与仓库声明语义一致；规范化内容 SHA-256 为 `5a3b2e52fe0ee6782e587e20d5508779385ee0016aaa546049338b57945877a6` |
| 普通问答 | 最终版本真实调用1次、2.93秒；按源码解释 seed=0 的随机行为，明确登记服务不自动补种子；无提案、声明和修订未变 |
| 非法整批修改 | 请求同时改示例温度0.2和种子0；调用1次、2.73秒，返回澄清，不部分保存温度 |
| 从资料编辑说明 | 提供一段采样温度说明，调用2次、4.763秒；只提议指定的 description，保留逐字引文和资料摘要，确认前声明不变，确认后增加一次修订 |
| 版本隔离 | 自定义说明写入草稿后，版本1导出返回409；显式改为版本2后可导出，返回 `exported_not_deployed`；加载的版本1内容保持不变，版本2仅为验收草稿，未纳入发布目录 |
| 数据保护 | 同步前后7份旧流程草稿及1份模型私有配置的文件 SHA-256 全部一致 |

以上耗时是对应服务调用观测值，不是性能评测。真实调用验收代码为 `4e06e74`，接口定义依据仍为声明中的 `source_reference.revision`；原始对话和测试导出保留在操作者的私有验收材料及服务草稿中，不纳入 Git。完整发布内容只以仓库声明文件为准。

验收也保留了负面结果：首次模型回答把 seed=0 推断成“未指定”的占位机制，已补入固定源码依据并复测；不能把一次问答通过视为所有解释都准确。规则、端口和导出合法性由服务端校验，不能由模型自报通过。旧原生“放弃编辑”确认框曾阻塞浏览器自动化，现已改为站内弹窗；该恢复弹窗改动后的完整浏览器回归、窄屏交互及外部 Coder 登录态不在本次已通过范围内。

本次未执行 AiiDA 提交、真实 ProteinMPNN GPU 推理、缓存／复用评估或科学效果评价。网页预览可用与声明可导出，均不代表这些链路已经接通。
