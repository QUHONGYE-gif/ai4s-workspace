# 任务声明与注册中心

本页统一维护约定①的声明规则、编辑确认及发布流程。完整定义只保存在 [ProteinMPNN v1 JSON](../configs/task_declarations/proteinmpnn/1.json)，由登记页和真实引擎共用 [DeclarationRegistry](../src/ai4s_declarations/registry.py)。当前支持 `single` 和 `mpnn_filter`；RFdiffusion、Boltz、MMseqs2 仅列为待接入。

## 使用与确认

沿用 [Agent 安装和启动](agent_demo_run.md#安装和启动)，从工作台侧栏进入任务注册中心 `workbench.html#/tasks`。工作流画布入口为 `#/workflows/editor`；旧 `#/workflows/new?mode=ai` 链接仍进入注册中心。

1. 从仓库版本“创建编辑副本”，或选择已支持任务及依据版本新建草稿。仓库定义只读，草稿可暂有缺项，保存在当前单用户服务的数据目录。
2. 逐项编辑名称、输入、参数、约束、输出和执行映射；也可上传资料、描述修改意图，由 Agent 生成提案。资料与例子不自动成为参数默认值。
3. 预览差异后显式确认。提案、问答、取消均不直接修改声明；后端校验整批修改，任一项无效则整批拒绝。确认使用修订号和操作编号，防止旧提案及重复确认覆盖新内容。
4. 完整校验后导出 `<version>.json`，响应附 SHA-256，状态为 `exported_not_deployed`。继续编辑会恢复草稿状态。修改已有正式版本的内容时须另定新版本，否则导出返回 409。
5. 将导出文件交发布负责人审核、入库和部署。网页导出不会自动发布、注册 Code 或提交实验。

声明草稿和工作流历史各有删除、回收站与恢复；正式仓库声明不提供网页删除。删除／恢复均增加修订，旧提案失效；恢复声明后须重新校验导出。删除最后一份工作流后保留空状态，刷新不补建示例。上传、已下载文件、其他草稿及科学结果不受影响。

删除／恢复按 `expected_revision` 检查，不缓存操作回执；网络重试出现冲突时刷新确认。回收站属于当前单用户原型，不承担跨成员权限管理。

## 声明与参数

声明字段包括 `schema_version`、`task_id`、`version`、`name`、`model`、`workflow_modes`、`inputs`、`parameters`、`constraints`、`execution`、`outputs`，以及可选的 `example`、`source_reference`。不接受任意命令、Python 插件或未知校验规则。

| 标识 | 含义 |
| --- | --- |
| `schema_version=ai4s-task-declaration-1` | 声明文件格式 |
| `task_id=proteinmpnn`、`version="1"` | 任务接口及其不可变版本；版本为最多 8 位的正整数字符串 |
| `model.release` | 模型部署版本；实际源码和权重仍由服务端按约定③核实 |
| `ai4s-artifacts-1` | 运行产物清单格式，与声明版本独立 |

输入 `pdb_file` 为必填 `SinglefileData`，内容为 PDB；Code、Computer、profile 与资源由部署端绑定。声明中的 `model_id=proteinmpnn`、`weights_family=vanilla` 和 release 是支持信息，不能单独证明实际运行身份。

推理参数由单任务和两阶段工作流共用：

| 参数 | 必填／默认 | 约束 |
| --- | --- | --- |
| `chains` | 必填，无默认 | 非空、非纯空白字符串 |
| `num_sequences` | 必填，无默认 | 正整数，不含原生序列；须能被 `batch_size` 整除 |
| `sampling_temperature` | 必填，无默认 | 有限正数 |
| `seed` | 必填，无默认 | `1..2**32-1` 的整数 |
| `model_name` | 默认 `v_48_020` | `v_48_002`、`v_48_010`、`v_48_020`、`v_48_030` |
| `batch_size` | 默认 `1` | 正整数 |
| `save_probabilities` | 默认 `true` | 布尔值 |

整数参数拒绝布尔值、小数和数字字符串；数值拒绝 NaN／无穷。只有表中三个可选项有执行默认值，示例内容不补齐必填项。

`mpnn_filter` 另要求 `score_threshold` 为有限数值、`top_k` 为正整数，均无默认值。筛选保留 `score <= score_threshold`，按 `(score, sample_id)` 升序取至多 `top_k` 条。阈值不限于 0–1，`top_k` 无须小于设计数；可返回少于要求或零条。空结果可正常结束，但不因此成为满足下游请求的候选。

## AiiDA 映射与产物

| 模式 | 入口 | 参数映射 |
| --- | --- | --- |
| `single` | `CalculationFactory("ai4s.proteinmpnn")` | `code`、`pdb_file`、`params=Dict(inference)` |
| `mpnn_filter` | `WorkflowFactory("ai4s.protein-mpnn-filter")` | `code`、`pdb_file`、`mpnn_params=Dict(inference)`、`filter_params=Dict(filter)` |

筛选参数不传入推理子任务；只改变筛选时可复用上游结果。实际参数检查、模型身份和提交接口见 [引擎说明](engine_service.md)，清单与文件校验见 [A 模块](aiida_tasks.md)，编排及重筛选见 [C 模块](../README_C.md)。

| 产物端口 | 类型 | 含义 |
| --- | --- | --- |
| `result` | `Dict` | 清单、样本和运行信息 |
| `artifacts.sequences` | `SinglefileData` | `design.fa`，含原生序列与设计序列 |
| `artifacts.scores` | `SinglefileData` | `scores.npz` |
| `artifacts.probabilities` | `SinglefileData`，条件输出 | `save_probabilities=true` 时的 `probabilities.npz` |
| `selected_sequences`、`sample_table`、`selection_report` | `Dict` | C 工作流的选中序列、样本表与执行报告 |

推理产物属于 CalcJob；两阶段工作流通过子过程或复用来源定位它们，不在根节点重复声明文件输出。`retrieved` 仅作诊断，不代替正式文件 Data。

## 发布与加载

发布负责人核对适配器支持、参数语义和真实端口后，将文件加入 `configs/task_declarations/<task_id>/<version>.json`，随代码审核和部署。同一 `(task_id, version)` 内容不可变；新任务需要自己的校验器和执行适配器，不能仅靠新增 JSON 获得执行能力。

加载器使用标准库，启动时校验所有声明；非法 JSON、重复字段、路径与标识不符或缺失必需基线会阻止加载。当前不热加载，也没有独立 HTTP 发布接口：

```python
from ai4s_declarations import DeclarationRegistry

registry = DeclarationRegistry("configs/task_declarations")
declaration = registry.get("proteinmpnn", "1")
```

未知任务或版本由 `get()` 抛出 `KeyError`，调用方映射为 `invalid_declaration`。返回定义为独立副本，编辑草稿不会改变已加载版本。

| API（相对 Agent 前缀） | 用途 |
| --- | --- |
| `GET /api/task-catalog` | 支持任务、依据版本、适配器和引擎接入状态 |
| `GET /api/task-declarations`、`GET /api/task-declarations/{task}/{version}` | 仓库版本列表与定义 |
| `GET/POST /api/declaration-drafts` | 草稿列表／创建；创建可选 `task_id`、`version` |
| `GET /api/declaration-drafts/{id}` | 草稿及修订 |
| `POST /api/declaration-drafts/{id}/{action}` | `preview`、`messages`、`confirm`、`cancel`、`export`、`delete`、`restore` |

写操作按接口传入 `expected_revision`、`operation_id`；删除列表通过 `?deleted=true` 查询。未知任务或依据版本在草稿创建时返回 422。旧草稿缺少依据元数据时仍按 ProteinMPNN v1 读取。

实现入口为 [草稿与确认 API](../src/ai4s_demo/declarations.py)、[Agent 提案](../src/ai4s_demo/declaration_agent.py) 和 [登记页面](../src/ai4s_demo/web/declaration.js)。正式 JSON 不包含密钥或服务器路径。

## 执行边界与验证

仓库版本已加载、草稿已导出、引擎已加载、任务可执行、已提交和已完成是独立状态。任务目录中的 `engine_status=not_connected` 指登记页面尚未绑定执行环境；真实 ProteinMPNN 通过 [真实实验入口](engine_service.md#使用与查询)提交。

工作流编辑器仍用三模型 `demo-1` 定义与参数；“确认节点配置”只保存演示快照。`num_seq_per_target`、`sampling_temp`、链策略及演示端口不自动等同真实的 `num_sequences`、`sampling_temperature`、`pdb_file`。正式节点联动需保存不可变声明引用及摘要、节点输入与参数，并由服务端按对应适配器校验；同一声明可供多个独立节点引用。

当前 [声明测试](../tests/test_task_declarations.py)覆盖协议约束、注册表副本、提案确认、修订冲突、导出及删除恢复。历史真实 DeepSeek 验证的环境、命令与结果保存在[固定版本登记记录](https://github.com/QUHONGYE-gif/ai4s-workspace/blob/50ab0954f1a72da3942ee620efc9733d021143b0/docs/task_declaration_run.md#验证记录)；本轮整理没有重新进行真实 LLM 或浏览器验收。真实引擎及跨成员科学任务证据见 [R007](../experiments/R007-member-reuse/record.md)，不能由登记页测试代替。

返回：[状态](status.md) · [Agent 接入](agent_demo_run.md) · [引擎](engine_service.md) · [仓库](../README.md)。
