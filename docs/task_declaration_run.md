# ProteinMPNN 任务声明登记与交付

本页面完成约定①的声明编辑、真实 Agent 提案、用户确认和 JSON 导出。声明规则以 [约定①](task_declaration_contract.md) 为准，完整声明文件为 [proteinmpnn/1.json](../configs/task_declarations/proteinmpnn/1.json)。当前支持真实任务接口的 `single` 和 `mpnn_filter` 定义；导出不等于引擎已登记，也不等于实验已提交。

## 使用入口

沿用 [Agent 工作流接入的启动方式](agent_demo_run.md#安装和启动)，在工作台选择 **工作流 → 接入自定义流程 → AI 辅助生成 → ProteinMPNN 任务登记 · 约定①**。原有三模型图编辑器在同一入口的“流程配置演示”中保留，数据独立，不将旧 Demo 字段直接当作真实 AiiDA 参数。

1. 新建空白声明，或从完整的已核实定义新建。草稿保存在现有 Agent 服务的数据目录 `declaration_drafts/`，不写入发布目录。
2. 页面展示输入、推理／筛选参数、必填性、真实默认值、范围、输出及所属阶段。展开“试填联调参数”可编辑示例；示例值与后端默认值分开。
3. 手动修改后点击“校验并预览修改”；也可粘贴／读取文本资料，向登记助手说明修改要求。真实 DeepSeek 调用需要先在页面配置 API；密钥仅存服务端，不包含在声明、公开响应及 Git 中。
4. 助手只生成提案。查看目标字段、旧值、新值和来源后，“确认并写入”整批保存；取消不改变已保存声明。普通问答不修改声明。缺项可保留为草稿，但不能导出；非法值和接口冲突整批拒绝，不部分保存。
5. “校验并导出声明”下载 `<version>.json`。缺项、类型错误、虚构默认值、不支持的端口／执行映射都会阻止导出。已发布版本内容不可覆盖，自定义内容需使用新接口版本；这不意味着新版本已经获团队批准。
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

已验证既有测试及新增声明测试：完整定义与协议附录一致，拒绝非法种子／类型／整除关系／未知字段，缺项阻止导出；预览不写入、取消不写入、确认只写一次、旧修订拒绝；同版本发布不可变、恢复缺项保留用户修改、非法 Agent 批次不部分保存、旧流程数据保持独立。模型替身测试仅验证程序机制，不作为真实 LLM 证据。

另外将推理规则与 `source_reference.revision` 指定的 A 模块源码逐字核对：14组合法／非法参数用例和3个真实后端默认值一致。筛选规则保持有限阈值、正整数 top_k，不增加0～1范围或生成条数上限。此项是接口一致性检查，不是模型效果评估。

浏览器与真实 DeepSeek 验证结果将在完成当前验收后补充；不以模拟回复替代真实调用。
