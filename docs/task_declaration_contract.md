# 约定① 任务声明

**约定① · 任务声明**　版本：`ai4s-task-declaration-1`　起草：陈铠洲　使用：曲鸿烨、邹佳轩

登记页操作、代码入口和验收边界见 [任务声明登记与交付](task_declaration_run.md)。

## 1　适用范围与职责

本轮只覆盖已接入 AiiDA 的真实 ProteinMPNN：`single` 单任务，以及 `mpnn_filter` 推理后接筛选。沿用 A 模块的 `ai4s-artifacts-1` 清单和真实输出端口。不把 RFdiffusion、Boltz、任意脚本导入、画布反馈环或通用工作流执行纳入本声明版本。

| 对象 | 负责什么 | 不混入本对象的信息 |
| --- | --- | --- |
| ① 任务声明 | 任务标识、支持的接口与模型版本、输入端口、参数规则、输出、调用映射 | 本次请求编号、运行 UUID、运行状态、缓存决定 |
| ② 实验请求 | 引用声明，提供本次输入、参数值、请求者与复用选择 | 不重新定义参数类型和默认值 |
| ③ 模型身份 | 提交时解析实际 release、源码提交和权重内容，形成模型身份与计算指纹 | 不信任 Agent 或浏览器自报的运行身份 |
| ④⑤ 候选与决定 | 合格候选、实际选择及理由 | 不在声明中预填未来结果 |

登记时写的是参数定义；实验时填写的是参数值。例如声明说明 `num_sequences` 是必填正整数，实验请求才填写 `4`。当前登记页已有的试填值可以经用户确认作为示例，不得无依据转换成引擎默认值。

## 2　顶层结构与版本

| 字段 | 类型 | 必填 | 含义与约束 |
| --- | --- | --- | --- |
| `schema_version` | string | 是 | 声明格式版本，固定为 `ai4s-task-declaration-1` |
| `task_id` | string | 是 | 本轮为 `proteinmpnn`，与②的 `declaration.task_id` 一致 |
| `version` | string | 是 | 本任务声明的接口版本；本版为 `"1"`，与②的 `declaration.version` 一致 |
| `name` | string | 是 | 人类可读名称，不作为模型内容身份 |
| `model` | object | 是 | `model_id`、声明适用的 `release`、`weights_family`；见下文 |
| `workflow_modes` | array[string] | 是 | 本轮为 `single`、`mpnn_filter` |
| `inputs` | object | 是 | 外部科学输入端口定义，见第3节 |
| `parameters` | object | 是 | `inference` 与 `filter` 两个参数定义分组，见第4节 |
| `constraints` | array[object] | 是 | 跨字段校验规则；仅支持预定义规则标识，不执行表达式或代码 |
| `execution` | object | 是 | 已有 AiiDA 插件及参数端口映射，见第5节；引擎须核对受支持项 |
| `outputs` | object | 是 | 按实际端口名定义输出及其所属阶段，见第6节 |
| `example` | object | 否 | 联调示例条件与具体参数；不是默认值，不参与运行身份计算 |
| `source_reference` | object | 是 | 声明依据的仓库、修订与文件路径；不等于模型身份③ |

三个版本的区分：`schema_version` 是声明文件格式；`version` 是任务接口版本；`model.release` 是声明适用的模型部署发布版本。`ai4s-artifacts-1` 则属于输出清单格式。接口 `version="1"` 与 A 清单的 `contract_version="1"` 在当前样例中对齐，但不把它们视为同一种版本或自动同步机制。

本轮 `model` 示例：

```json
{
  "model_id": "proteinmpnn",
  "release": "8907e667-py312-torch260cu124",
  "weights_family": "vanilla"
}
```

这里的 `release` 来自当前任务 Parser 的 `EXPECTED_RELEASE`，表示声明适用范围，**不是提交时已经核实的模型身份**。实际身份按③从服务端部署与 manifest 解析。已知版本不一致时不能继续宣称该声明匹配；③所述身份无法解析时的禁止缓存规则仍由引擎实现，登记页不自行替换该规则。当前 Parser 固定检查此 release，不能仅通过改声明字符串就支持新的模型发布版本。

同一 `(task_id, version)` 发布后内容应不可变；变更参数语义、默认值、端口或执行映射时发布新版本并保留旧请求的引用。变更由起草人与使用人核对，曲鸿烨统一发布。

## 3　输入端口

| 端口 | AiiDA 类型 | 文件格式 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `pdb_file` | `SinglefileData` | PDB | 是 | 一个输入骨架文件；执行时复制为 `input.pdb` |

声明描述端口类型，不放上传编号、个人绝对路径或实际文件内容。一次实验的具体输入沿用②：`inputs.pdb_file` 使用上传引用或已有节点 UUID。文件编号是否存在、内容是否可读、链是否存在，要在获得实际文件后另行检查；不能仅凭声明中的 `format=PDB` 判断输入合格。

原生计算还需要 `code` 与 `params`。`code` 由引擎绑定已配置且受支持的 Code；`params` 按第5节由请求构造。它们不是要求普通用户上传的文件端口。profile、Computer、资源和 Code UUID 留在服务端部署配置中。

## 4　参数规则

字段名按 A/C 的实际接口统一，不直接使用 ProteinMPNN CLI 名称。类型使用 `string`、`integer`、`number`、`boolean`；`integer` 不接受小数、布尔值或数字字符串，数值不得为 NaN／Infinity。`required` 指实验请求是否必须明确提供；有默认值的可选项在提交前补齐。

### 4.1　推理参数：`parameters.inference`

| 名称 | 类型 | 请求必填 | 后端默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `chains` | string | 是 | 无 | 非空且不能仅含空白；本轮真实验收为 `A` |
| `num_sequences` | integer | 是 | 无 | ≥1，且为 `batch_size` 的整数倍；不计原生序列 |
| `sampling_temperature` | number | 是 | 无 | 单个有限正数；不接受多温度字符串 |
| `seed` | integer | 是 | 无 | 1–4294967295；不允许以0表示随机种子 |
| `model_name` | string | 否 | `"v_48_020"` | 枚举：`v_48_002`、`v_48_010`、`v_48_020`、`v_48_030`；实际权重存在性由引擎核实 |
| `batch_size` | integer | 否 | `1` | ≥1；本轮验收使用1 |
| `save_probabilities` | boolean | 否 | `true` | 是否请求保存概率输出 |

只有后三项来自 `PARAMETER_DEFAULTS`。提交脚本虽然为链、条数和温度设置了命令行示例默认值，但 A 的参数校验仍要求它们存在，所以本声明不给前四项发明后端默认值，也不把它们的 `default` 写为 `null`。

跨字段规则表示为：

```json
{"rule":"num_sequences_multiple_of_batch_size","scope":"inference","message":"num_sequences 必须为 batch_size 的整数倍。"}
```

参数元信息使用 `label`、`type`、`required`、`category`、`description`，以及适用时的 `default`、`enum`、`minimum`、`maximum`、`exclusiveMinimum`、`minLength`。它们是本声明的受限元信息，不声称是一份完整 JSON Schema。空白链检查、有限数检查和整除检查由对应已知校验逻辑实现，不使用 `eval`。

### 4.2　筛选参数：`parameters.filter`

| 名称 | 类型 | 两阶段请求必填 | 后端默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `score_threshold` | number | 是 | 无 | 有限数；保留 `score <= score_threshold` 的设计记录 |
| `top_k` | integer | 是 | 无 | ≥1；按 `(score, sample_id)` 升序最多取前 `top_k` 条 |

`workflow=single` 时不填写 `params.filter`；`workflow=mpnn_filter` 时提供两个筛选值。`0.82`、`2` 是统一示例，不是 C 模块默认值。不增加源码不存在的“阈值必须在0到1之间”或“top_k 不能大于生成数”等限制；符合阈值的样本不足时可能少于 top_k。

参数分类决定其去向：推理参数传给 ProteinMPNN；筛选参数只传给筛选阶段。只改筛选参数不会改变子 CalcJob 的推理参数，但两阶段流程自身的输入已变化；不能据此宣称整个流程指纹不变。

### 4.3　补默认值与未知字段

先按类型检查用户值，再补齐缺失的三个可选推理项，执行枚举、范围和跨字段检查；归一化后的完整参数交给②③。对同义请求使用相同完整参数，避免因省略默认值而产生不同输入。

声明加载、登记页及引擎服务必须拒绝未知字段、未知规则和不支持的插件，不静默忽略。A 已拒绝未知推理参数；固定源码版本的 C 筛选检查尚未明确拒绝额外键，因此服务端在构造 C 的输入前，按本约定完成筛选字段检查。

## 5　约定②到 AiiDA 的映射

| ② 中的字段／服务端配置 | `single` | `mpnn_filter` |
| --- | --- | --- |
| 任务入口 | Calculation `ai4s.proteinmpnn` | WorkChain `ai4s.protein-mpnn-filter` |
| 服务端选定的 Code | `builder.code` | `builder.code`，再由 WorkChain 传给子计算 |
| `inputs.pdb_file` 解析后的文件节点 | `builder.pdb_file` | `builder.pdb_file` |
| 补齐默认值的 `params.inference` | `builder.params`，类型 `Dict` | `builder.mpnn_params`，类型 `Dict` |
| `params.filter` | 不适用 | `builder.filter_params`，类型 `Dict` |

JSON 示例用 `execution` 显式记录这组固定映射。它是服务端已知适配器的描述，不是授权浏览器传入任意入口或命令；引擎按批准的 `(task_id, version)` 解析并核对，不能执行 Agent 生成的 Shell。

ProteinMPNN CLI 的 `--num_seq_per_target`、`--sampling_temp` 等由现有 A CalcJob 转换；网页提交仍用 `num_sequences`、`sampling_temperature`。不在①中再创建一套彼此独立的 CLI 拼接规则。

## 6　输出端口与阶段归属

以下是成功任务的输出接口声明，不是已生成文件或节点的记录。`owner` 表示输出所属阶段：`inference` 指单任务 CalcJob，或两阶段流程中的推理子 CalcJob；`filter` 指两阶段 WorkChain 的筛选输出。

| 端口 | owner | AiiDA 类型／文件 | 成功时要求 |
| --- | --- | --- | --- |
| `result` | inference | `Dict`，`ai4s-artifacts-1` | 必须；含清单、内联样本与运行记录 |
| `artifacts.sequences` | inference | `SinglefileData`，`design.fa`／FASTA | 必须；包含原生和设计记录 |
| `artifacts.scores` | inference | `SinglefileData`，`scores.npz`／NPZ | 必须；设计样本的分数 |
| `artifacts.probabilities` | inference | `SinglefileData`，`probabilities.npz`／NPZ | 生效 `save_probabilities=true` 时必须 |
| `retrieved` | inference | 原生 `FolderData` | 诊断目录；不作为本声明的必需科学产物 |
| `selected_sequences` | filter | `Dict` | 两阶段正常完成时必须；当前不是 FASTA |
| `sample_table` | filter | `Dict` | 两阶段正常完成时必须 |
| `selection_report` | filter | `Dict` | 两阶段正常完成时必须；部分失败也可能有报告，不能据此判断成功 |

`outputs` 的必填元信息为 `owner`、`aiida_type`、`required`、`role`、`description`。文件输出另有 `format`、`filename`；概率输出另有 `required_if={"path":"params.inference.save_probabilities","equals":true}`。先补默认值再判断条件；`required=false` 不代表条件成立时也可缺失。条件仅支持这一受限的字段相等判断，不执行代码。`owner=filter` 的要求只对 `mpnn_filter` 生效。

**两阶段 WorkChain 当前没有直接暴露 `result`／`artifacts.*` 根输出。**引擎服务需沿其推理子 CalcJob 查询这些产物，再组装②的状态；不能把本表理解为全部端口都直接位于 `WorkChain.outputs`。C 当前筛选读取的是清单中的内联样本，而不是直接打开序列与分数文件节点。端口归属按该实际结构映射。

约定②第4节已经确定对网页返回 `outputs.result`、`outputs.artifacts`，两阶段另有 `outputs.selected_sequences` 和 `outputs.selection_report`。这里补充的是实际 AiiDA 输出到这套结构的映射，不要求②新增字段。①中的 `sample_table` 是已有 C 输出的接口描述，不等于②必须新增同名状态字段；`owner` 也只是①的阶段归属元信息。

筛选为空时沿用现有约定：

- 按②第5节，若过程正常结束且 exit_status=0，请求状态为 `finished`；筛选为空本身不自动变成 `failed`。
- 按④第3.1节，作为筛选结果候选必须“筛选后非空”。空的筛选结果集不合格，`qualified=false`；按其逐项判定顺序，可在完整性检查处记录 `insufficient: 筛选后结果为空`，保留未通过原因。这里是应用既有枚举的示例，不增加理由编码。
- 按④第3.2节，候选按结果集区分；筛选结果集不合格，不代表其上游完整的 ProteinMPNN 推理结果也不合格。上游是否可复用应按其自身条件另行判定。
- 按⑤第2.1节和理由码 R02，允许复用但该决策阶段无合格候选时决定重算；不选中不合格的空筛选结果。此规则不是“筛选为空就无限重试”或擅自换种子的授权，新采样仍由用户选择和⑤决定。

例如推理生成了4条有效序列，但阈值0.82下一条也未入选：网页可以显示“已完成，筛选通过0条”；空筛选结果集不能作为合格筛选候选。原始4条推理结果的资格仍独立核对，避免把它们一并丢弃或无依据地要求重新推理。

不新增不存在的 `artifact_manifest`、`execution_report` 或筛选 FASTA 端口。实际结果 UUID、位置与大小由执行／查询阶段填写；复用决定由⑤记录，`selection_report` 不替代⑤。

## 7　声明示例与请求引用

完整机器可读声明见文末附录，对应仓库文件为 [`configs/task_declarations/proteinmpnn/1.json`](../configs/task_declarations/proteinmpnn/1.json)。示例使用真实任务接口及 1CRN、A 链、4条设计、batch_size=1、非零种子41，包含可选概率输出和两阶段筛选定义。`example` 中的温度0.1、阈值0.82与 top_k=2 均需作为示例看待。

实验页引用它时，②中的关键片段为：

```json
{
  "declaration":{"task_id":"proteinmpnn","version":"1"},
  "workflow":"mpnn_filter",
  "params":{
    "inference":{"chains":"A","num_sequences":4,"sampling_temperature":0.1,"seed":41},
    "filter":{"score_threshold":0.82,"top_k":2}
  }
}
```

这只是②请求的节选，不能单独提交；完整请求还必须包含②规定的版本、请求者、真实输入引用及复用选择。上传编号必须先通过真实上传取得，不提供看起来可用的虚构 UUID 或上传编号。

①中的 `example` 不是请求，也不意味着输入已上传。①的接口规则经发布后可重复使用；修改某一次实验的具体参数值应生成②请求，不应每次改写同一版本的声明。

## 8　登记、确认和导出

1. 读取已批准接口定义及对应资料，核对声明版本和模型标识；动态登记来源必须保留仓库修订和具体文件。
2. 页面按声明分组展示输入、推理参数、筛选参数、输出；区分必填、默认值、示例值和已填值。用户编辑具体值时按同一规则校验。
3. Agent 可以解释和提出补全提案。普通问答保持声明与参数值不变；写入前展示目标、旧值、新值和依据，由用户明确确认后整批写入。否定、含糊数量、多个同名节点或存在非法字段时先澄清，不擅自补值，也不部分保存。
4. 默认值只能来自被支持任务的已核实定义；来源文档不一致时标出差异，不让 Agent 靠常识选择。用户想用不同参数值时记录为实验值或示例，不冒充模型默认值。超出受支持接口的端口／参数需要更新适配器和审定声明，不能仅由 Agent 改出一个新字段就声称已支持。
5. 导出前校验声明元信息、端口、类型、默认值合法性、阶段归属和已知映射。导出声明本身不要求先存在真实输入文件或填好一次实验的全部参数值；必填参数定义完整即可。若导出包含 `example`，其中具体值也应合法。
6. 声明按第9节随引擎服务部署并加载。实验页沿用②的 `declaration.task_id + declaration.version` 引用它；不存在或版本不符时返回 `invalid_declaration`。声明生成、被引擎登记、请求提交、科学执行完成分别报告。

声明问题对应②的 `invalid_declaration`；具体参数值问题对应 `invalid_params`；输入引用不存在对应 `input_not_found`。不另行改变②状态枚举。

## 9　声明登记、加载与请求衔接

### 9.1　文件位置与交付

本轮采用**声明文件随引擎服务部署，启动时校验并加载**的方式，不设置独立的声明注册 HTTP 接口。部署目录固定为仓库相对路径 `configs/task_declarations/`：

```text
configs/task_declarations/
└── proteinmpnn/
    └── 1.json
```

每个文件对应一份声明，文件路径为 `<task_id>/<version>.json`，目录名、文件名必须与文件内的 `task_id`、`version` 一致。声明是普通 JSON 数据文件，不包含密钥、服务器绝对路径或可执行命令。

| 责任人 | 交付与职责 |
| --- | --- |
| 陈铠洲 | 核对真实接口，提供约定①、完整 JSON 文件及登记页／Agent 的声明导出 |
| 曲鸿烨 | 审阅并统一发布声明；将文件纳入引擎部署，实现加载、查找、参数检查及受支持适配器映射 |
| 邹佳轩 | 使用同版本声明生成实验表单，按②提交引用、输入与参数，展示返回状态及结果 |

网页导出的声明经审阅后进入部署目录；导出本身不会立即改变运行中的引擎。文件经团队既有分支与审阅流程交付，不绕过项目的 `main` 合并约定。引擎部署与实验页使用同一发布版本的声明。

### 9.2　启动校验与登记

引擎服务启动时读取部署目录，完成全部声明的校验后，建立以 `(task_id, version)` 为键的只读查找表。登记成功表示声明已被引擎校验并可查找，不表示已创建或运行 AiiDA 任务。

加载时检查：

1. JSON 可解析，格式版本受支持，必填字段及字段类型完整；未知字段或规则不被静默忽略。
2. 文件位置与 `task_id/version` 对应；本轮须存在 `proteinmpnn/1.json`。标识、版本和加载路径只按已部署的文件建立索引，不使用请求值拼接文件路径读取。
3. 同一 `(task_id, version)` 不重复登记；不得用后读到的文件覆盖先前文件。
4. 输入输出端口、参数类型、默认值、条件输出和阶段归属符合本约定，并与受支持任务适配器一致。
5. `execution` 的入口和映射处于引擎支持范围；声明文件不能自行授权新的插件、Shell 命令或模型执行。

任何声明校验失败时，本次服务启动失败，日志记录文件、字段和原因；不能跳过非法声明后报告启动成功。成功日志记录加载的声明标识、版本及对应文件，供部署核对。

服务运行期间不自动热加载目录变化。新增或升级声明随引擎服务按现有维护流程部署、重新加载；部署前保护在途请求。同一已发布版本不原地改写，旧请求保留原声明引用。

### 9.3　实验请求处理

实验页提交②规定的引用：

```json
{"declaration":{"task_id":"proteinmpnn","version":"1"}}
```

服务从已加载的查找表中取得声明，检查所选 `workflow`、输入引用和具体参数，补齐默认值后，按第5节构造 AiiDA 输入，再由③解析实际模型身份并进入执行／复用链路。实际身份不由声明中的展示信息或 Agent 自报值代替。

声明不存在或版本不符时，沿用②的 `invalid_declaration`，不创建 AiiDA 过程。具体参数问题使用 `invalid_params`，输入引用不存在使用 `input_not_found`；引擎服务整体不可用时按②处理 `engine_unavailable`。网页不能通过请求附带另一份声明正文覆盖服务端登记内容。

### 9.4　与其他约定保持一致

| 对接事项 | 已有依据 | 本约定的衔接 |
| --- | --- | --- |
| 声明引用与失配处理 | ②第3、5节 | 使用 `task_id + version`；失配返回 `invalid_declaration` |
| 实际模型身份 | ③第3、5节 | ①声明支持范围；实际部署身份由服务端解析 |
| 对网页的结果字段 | ②第4节 | 从对应阶段节点取值，组装既定的 `result`、`artifacts` 及两阶段结果字段 |
| 空筛选结果的资格 | ④第3.1、3.2节 | 空筛选结果集不合格；上游推理结果独立判断；过程状态仍按② |
| 无合格候选的决定 | ⑤第2.1节与 R02 | 允许复用且无合格候选时重算，保留候选和原因，不新增复用策略或理由码 |

### 9.5　验收清单

- 声明 JSON 可解析，`task_id/version` 能与②引用一一匹配；不含密钥、个人路径、虚构运行 UUID。
- 参数元信息与固定源码版本一致；三个可选推理默认值准确，示例值未冒充默认值。
- `single` 和 `mpnn_filter` 均能正确映射 AiiDA 输入；筛选参数不进入 ProteinMPNN 子计算参数。
- 缺少 `chains`、种子为0、序列数为小数、温度为非正或非有限数、序列数不整除 batch_size 时，具体实验校验明确失败。
- `save_probabilities=false` 时不要求概率输出；省略该项时先补 `true`，成功结果须提供概率输出。
- 筛选阈值采用 `<=`；`top_k` 为正整数；没有足够合格样本时不伪造结果。空筛选结果集按④判为不合格，保留原因；正常结束的过程仍按②表示为 `finished`，不连带否定上游推理结果。
- 真实 Agent 普通问答不改声明；明确修改提出提案、确认后写入；缺项、取消确认和非法值都有可核对记录。
- 引擎启动日志能核对 `proteinmpnn/1.json` 已加载；缺少基线声明、重复标识或非法声明时启动失败；不存在的声明版本按②返回 `invalid_declaration`。
- 引擎实际加载同一份声明，网页导出的②请求能完成解析和提交；提交成功与模型执行成功分别提供证据。

上述条目是实现验收要求；协议文件定稿不等于登记页、引擎加载或科学运行已通过验收。


## 附录　ProteinMPNN 完整任务声明 JSON

以下内容与 `configs/task_declarations/proteinmpnn/1.json` 一致，可复制保存为该文件，随引擎服务部署。`example` 是联调示例，不能作为已上传输入或默认参数；实际实验按②另行提交。

```json
{
  "schema_version": "ai4s-task-declaration-1",
  "task_id": "proteinmpnn",
  "version": "1",
  "name": "ProteinMPNN 蛋白质序列设计",
  "model": {
    "model_id": "proteinmpnn",
    "release": "8907e667-py312-torch260cu124",
    "weights_family": "vanilla"
  },
  "workflow_modes": [
    "single",
    "mpnn_filter"
  ],
  "inputs": {
    "pdb_file": {
      "label": "输入骨架",
      "aiida_type": "SinglefileData",
      "format": "PDB",
      "required": true
    }
  },
  "parameters": {
    "inference": {
      "chains": {
        "label": "设计链",
        "type": "string",
        "required": true,
        "category": "inference",
        "description": "PDB 中待设计的链；本轮验收使用 A。",
        "minLength": 1
      },
      "num_sequences": {
        "label": "设计序列数",
        "type": "integer",
        "required": true,
        "category": "inference",
        "description": "设计记录数，不计原生序列记录；须为 batch_size 的整数倍。",
        "minimum": 1
      },
      "sampling_temperature": {
        "label": "采样温度",
        "type": "number",
        "required": true,
        "category": "inference",
        "description": "单个有限正数。",
        "exclusiveMinimum": 0
      },
      "seed": {
        "label": "随机种子",
        "type": "integer",
        "required": true,
        "category": "inference",
        "description": "非零种子；新采样的实际种子由决策环节生成并回传。",
        "minimum": 1,
        "maximum": 4294967295
      },
      "model_name": {
        "label": "权重名",
        "type": "string",
        "required": false,
        "category": "inference",
        "description": "当前真实任务支持的 vanilla 权重名；实际文件须由引擎核实。",
        "default": "v_48_020",
        "enum": [
          "v_48_002",
          "v_48_010",
          "v_48_020",
          "v_48_030"
        ]
      },
      "batch_size": {
        "label": "批大小",
        "type": "integer",
        "required": false,
        "category": "inference",
        "description": "正整数；本轮验收使用 1。",
        "default": 1,
        "minimum": 1
      },
      "save_probabilities": {
        "label": "保存概率",
        "type": "boolean",
        "required": false,
        "category": "inference",
        "description": "控制是否请求并发布概率文件。",
        "default": true
      }
    },
    "filter": {
      "score_threshold": {
        "label": "分数阈值",
        "type": "number",
        "required": true,
        "category": "filter",
        "description": "有限数；保留 score 小于或等于此阈值的设计记录。"
      },
      "top_k": {
        "label": "最多保留条数",
        "type": "integer",
        "required": true,
        "category": "filter",
        "description": "按 (score, sample_id) 升序，最多保留 top_k 条；不是保证产出条数。",
        "minimum": 1
      }
    }
  },
  "constraints": [
    {
      "rule": "num_sequences_multiple_of_batch_size",
      "scope": "inference",
      "message": "num_sequences 必须为 batch_size 的整数倍。"
    }
  ],
  "execution": {
    "calculation_entry_point": "ai4s.proteinmpnn",
    "workflow_entry_point": "ai4s.protein-mpnn-filter",
    "inference_parameter_port": {
      "single": "params",
      "mpnn_filter": "mpnn_params"
    },
    "filter_parameter_port": "filter_params",
    "code_binding": "engine_configured"
  },
  "outputs": {
    "result": {
      "owner": "inference",
      "aiida_type": "Dict",
      "required": true,
      "schema_version": "ai4s-artifacts-1",
      "role": "manifest",
      "description": "清单、内联样本、分数、运行身份及校验结论。"
    },
    "artifacts.sequences": {
      "owner": "inference",
      "aiida_type": "SinglefileData",
      "format": "FASTA",
      "filename": "design.fa",
      "required": true,
      "role": "primary",
      "description": "包含原生序列和设计记录；原生序列不计入 num_sequences。"
    },
    "artifacts.scores": {
      "owner": "inference",
      "aiida_type": "SinglefileData",
      "format": "NPZ",
      "filename": "scores.npz",
      "required": true,
      "role": "auxiliary",
      "description": "与设计样本对应的分数数组。"
    },
    "artifacts.probabilities": {
      "owner": "inference",
      "aiida_type": "SinglefileData",
      "format": "NPZ",
      "filename": "probabilities.npz",
      "required": false,
      "required_if": {
        "path": "params.inference.save_probabilities",
        "equals": true
      },
      "role": "auxiliary",
      "description": "请求保存时必须提供并通过概率及样本对应检查。"
    },
    "retrieved": {
      "owner": "inference",
      "aiida_type": "FolderData",
      "required": false,
      "role": "diagnostic",
      "description": "AiiDA 原生取回目录，保存运行记录和日志；不新增同义端口。"
    },
    "selected_sequences": {
      "owner": "filter",
      "aiida_type": "Dict",
      "required": true,
      "role": "primary",
      "description": "两阶段流程的筛选记录，当前不是 FASTA 文件；entries 可能为空，其候选资格按约定④判断，过程状态按约定②判断。"
    },
    "sample_table": {
      "owner": "filter",
      "aiida_type": "Dict",
      "required": true,
      "role": "auxiliary",
      "description": "两阶段流程的筛选样本与筛选条件。"
    },
    "selection_report": {
      "owner": "filter",
      "aiida_type": "Dict",
      "required": true,
      "role": "report",
      "description": "两阶段流程的筛选数量和执行摘要；不代替约定⑤。"
    }
  },
  "example": {
    "input_description": "真实 1CRN PDB，A 链；示例不携带可直接提交的上传编号。",
    "workflow": "mpnn_filter",
    "params": {
      "inference": {
        "chains": "A",
        "num_sequences": 4,
        "sampling_temperature": 0.1,
        "seed": 41,
        "model_name": "v_48_020",
        "batch_size": 1,
        "save_probabilities": true
      },
      "filter": {
        "score_threshold": 0.82,
        "top_k": 2
      }
    }
  },
  "source_reference": {
    "repository": "QUHONGYE-gif/ai4s-workspace",
    "revision": "8b9569f627957cfde6879cddd01e802d4619e778",
    "paths": [
      "docs/aiida_tasks.md",
      "src/ai4s_tasks/proteinmpnn.py",
      "src/ai4s_tasks/proteinmpnn_outputs.py",
      "src/ai4s_workflows/workflows.py",
      "src/ai4s_workflows/filtering.py",
      "src/ai4s_tasks/submit.py",
      "pyproject.toml"
    ]
  }
}
```
