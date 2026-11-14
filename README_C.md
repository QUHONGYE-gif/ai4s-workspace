# C 模块：编排、复用与恢复

`ProteinMPNNFilterWorkChain` 将推理 CalcJob、产物门禁和筛选 calcfunction 串成两阶段工作流，通过 AiiDA 原生等待与持久化上下文运行。真实推理使用 [A 模块](docs/aiida_tasks.md)，模型身份、固定内核、跨成员传递与 HTTP 入口统一见 [引擎服务](docs/engine_service.md)。当前进展见 [状态](docs/status.md)。

## 公共端口与提交

| 端口 | 方向／类型 | 用途 |
| --- | --- | --- |
| `code` | 输入 `AbstractCode` | 真实推理 `ai4s.proteinmpnn`，mock 为 `ai4s.light-mpnn` |
| `pdb_file` | 输入 `SinglefileData` | 结构输入，按内容校验 |
| `mpnn_params` | 输入 `Dict` | 推理参数 |
| `filter_params` | 输入 `Dict` | `score_threshold`、`top_k`，不传入推理任务 |
| `existing_mpnn_result` | 可选输入 `Dict` | 旧结果入口，用于只重筛选；与决策端口互斥 |
| `request_id`、`reuse_policy` | 可选输入 `Str` | 成对提供，分别为 `req-<UUID>` 及三种复用策略 |
| `reuse_candidates` | 可选输入 `List` | 约定④完整候选，包含不合格项 |
| `candidate_results` | 可选输入 `Dict` | `<结果UUID>::<完整fingerprint>` 到同一结果 UUID 的映射 |
| `decision_function` | 可选输入 `Str` | daemon 可导入的可信 `module:function` |
| `selected_sequences` | 输出 `Dict` | `entries`：选中样本和序列 |
| `sample_table` | 输出 `Dict` | `rows`、筛选阈值和 `top_k` |
| `selection_report` | 输出 `Dict` | 状态、决策、实际种子、尝试和缓存来源 |

先按[独立环境说明](docs/engine_service.md#独立安装与启动)准备统一内核、本人 profile 与 daemon。以下示例需将 Code 标签和 PDB 路径替换为目标环境的真实配置；参数约束见[任务声明](docs/task_declarations.md#声明与参数)。

```python
from aiida import load_profile, orm
from aiida.engine import submit
from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain

load_profile()
builder = ProteinMPNNFilterWorkChain.get_builder()
builder.code = orm.load_code("proteinmpnn-8907e667@localhost")
builder.pdb_file = orm.SinglefileData(file="/实际路径/1CRN.pdb")
builder.mpnn_params = orm.Dict(dict={
    "chains": "A", "num_sequences": 4,
    "sampling_temperature": 0.1, "seed": 41,
})
builder.filter_params = orm.Dict(dict={"score_threshold": 0.82, "top_k": 2})
builder.metadata.label = "proteinmpnn-filter-1crn-seed41"
node = submit(builder)
print(node.uuid)
```

`submit_workchain()` 使用合成 PDB 和 mock 参数，只作演示；mock 有 40% 随机失败概率，不代表真实模型可靠性。新增插件或修改代码后，刷新本人专用环境的 editable 安装并重启本人 daemon，已有终态节点保持不变。

## 复用策略与记录

WorkChain 的 `get_reuse_configuration()` 向统一内核提供请求上下文及 `ReuseMaterialization.CONSUME_CANDIDATE`。内核产生唯一决定后，WorkChain 再核对策略、过程、种子、候选和注入结果；重算明确禁用缓存。

| 策略 | 默认动作与种子 | 理由码 |
| --- | --- | --- |
| `allow_reuse`，存在合格候选 | 按顺序选择第一条；原种子直接消费结果，不创建 CalcJob | R01 |
| `allow_reuse`，无合格候选 | 原参数、原种子重算 | R02 |
| `force_rerun` | 原参数、原种子重算，仍保留全部候选供审计 | R03 |
| `new_sample` | 使用不同于原值的 `1..2**32-1` 整数种子重算 | R04 |
| 可信自定义决策器 | 仅在用户策略允许的动作范围内选择 | R05 |

决策端口要求有效的 `mpnn_params.seed`。`request_id`、`reuse_policy` 不完整，或与 `existing_mpnn_result` 混用时返回 208。调用方按约定④构造候选后，可在提交前设置：

```python
builder.request_id = orm.Str("req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e")
builder.reuse_policy = orm.Str("allow_reuse")
builder.reuse_candidates = orm.List(list=[candidate])
builder.candidate_results = orm.Dict(dict={
    f"{candidate['uuid']}::{candidate['fingerprint']}": candidate["uuid"],
})
```

候选 `uuid` 指结果 `Dict`，来源 CalcJob UUID 另行记录。`(uuid, fingerprint)` 唯一；候选保留成员、位置、大小、耗时与资格。不合格 `reason` 以 `missing_file`、`format_error`、`insufficient`、`below_threshold`、`not_finished` 或 `manual_reject` 开头，合格项为 `null`。选中结果须可加载、UUID 一致、有原生来源并通过下述门禁；映射缺失、歧义或不一致返回 209。

决策以 `ai4s-decision-1` 保存到节点 extras 的 `ai4s_decision_records`，字段为 `request_id`、`process_uuid`、`reuse_policy`、完整 `candidate_compare_list`、`final_decision`（action、selected_candidate_uuid、effective_seed）、`reason`（reason_code、reason_text）及 UTC `timestamp`。同一请求与过程重放替换原记录；同一请求的不同过程保留各自记录。只读取通过结构及策略校验的记录：

```python
from ai4s_workflows.decision import find_decisions_by_request, find_decisions_by_process

records = find_decisions_by_request("req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e")
# 或 find_decisions_by_process(node.uuid)
```

也可使用 B 模块 `python -m ai4s_query.cli decision <请求或过程UUID>`。候选和记录字段与[约定④](https://lcnzinmktf6r.feishu.cn/wiki/YH74w7cq6iZLdVkpVBBcMEtcnlc)、[约定⑤](https://lcnzinmktf6r.feishu.cn/wiki/WRgGwqdcKiqvFNkwqSscY7pMn8c)对齐。

自定义函数接收 `request_id`、`process_uuid`、`reuse_policy`、`candidate_compare_list`、`original_seed`，返回四字段：

```python
def choose(context):
    return {
        "action": "rerun",
        "selected_candidate_uuid": None,
        "effective_seed": context["original_seed"],
        "reason_text": "现有候选证据不足",
    }
```

将经过审查的函数配置为 `builder.decision_function = orm.Str("my_decisions:choose")`。`allow_reuse` 仅允许 reuse／rerun，force_rerun 仅允许 rerun，new_sample 仅允许 new_sample；不能选择不合格项、复用换种子或重算换种子。

## 门禁、重筛选与失败处理

推理结果必须来自成功结束的相应 CalcJob，满足 Code 配置与模型身份、PDB 内容及补齐默认值后的推理参数一致性，并通过清单 schema、当前 Parser 校验、正式文件端口与样本映射检查。跨成员比较已核实的 Code 内容，不要求 Computer UUID 相同。具体文件和数值校验由 [A 模块](docs/aiida_tasks.md)维护。

确定性门禁失败不重跑模型；CalcJob 失败或确认没有外部作业的提交失败，最多进行两次总尝试。稳定 label 为 `ai4s-mpnn:<WorkChain UUID>:<两位尝试号>`。提交异常先按 label 核对；存在外部作业或查询失败则返回 207，不重复提交。

| 退出码 | 含义 |
| --- | --- |
| 201 | 不支持的产物版本 |
| 202 | 已达到尝试上限 |
| 203 | 缺少推理输出 |
| 204 | 产物 schema 不符 |
| 205 | 推理计算失败 |
| 206 | 清单不合格或上游身份不符 |
| 207 | 提交状态不明 |
| 208 | 复用请求不完整、互斥或无效 |
| 209 | 无法唯一定位或加载选中结果 |

`selection_report.attempts` 保存尝试号、label、CalcJob PK／UUID、状态、退出码、缓存来源与创建计数；失败报告保留原因。成功复用时 `selected_candidate_uuid` 是结果 UUID，`cached_from` 是来源过程 UUID。`model_launches` 和 `count_mpnn_launches()` 统计 CalcJob 节点，不能代替实际模型执行次数。

仅改变筛选时，调用 `rerun_filter_only(node.pk, new_top_k=3, new_threshold=0.83)`。新 WorkChain 引用原 Code、PDB、推理参数和结果 Data，筛选 calcfunction 有独立 creator。验收同时检查上游 UUID 一致、零新 CalcJob、零尝试以及外部程序计数未增加。

## 恢复与验证

用 `verdi process show <UUID>`、`verdi process report <UUID>` 和 `python -m ai4s_workflows.recovery --workchain <PK>` 检查完成状态；提交返回 UUID 不等于成功。

停止本人 daemon 前记录过程身份和状态。daemon 停止期间排队的任务应保持等待，重启后由原队列继续；direct 作业可能仍在操作系统执行，应先检查原生状态与取回目录，再决定等待、`verdi process play <PK>` 或诊断。提交没有返回 UUID 时用 `python -m ai4s_workflows.recovery --label '<label>'` 核对，确认没有外部作业后再决定重提。

在统一内核的专用 Python 3.12 环境运行：

```bash
python -m pytest -q
python tests/test_engine_kernel.py
python tests/test_aiida_workflows.py
```

后两项创建独立临时 profile；工作流检查使用 CPU mock，涵盖重试、门禁、仅重筛选、提交核对及 POSIX daemon 排队／停启恢复，不构成真实模型中断恢复验收。真实跨成员验证入口为 [verify_member_reuse.py](scripts/verify_member_reuse.py)，命令、实际环境、文件与原生节点核对见 [R007](experiments/R007-member-reuse/record.md)；历史 GPU 三策略与重筛选证据见 [R005](experiments/R005-aiida-proteinmpnn/record.md)。

返回：[A 模块](docs/aiida_tasks.md) · [任务声明](docs/task_declarations.md) · [引擎](docs/engine_service.md) · [状态](docs/status.md) · [仓库](README.md)。
