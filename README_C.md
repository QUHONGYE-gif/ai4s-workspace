# C模块：编排、重算与恢复

当前受控复用通过统一 AiiDA 内核执行，候选与记录约定见[复用决策](docs/reuse_decision.md)；模型身份、跨成员归档传递和真实验证见[引擎服务](docs/engine_service.md)与[R007](experiments/R007-member-reuse/record.md)。

当前提供推理 CalcJob → 清单门禁 → 筛选 calcfunction 的两阶段 WorkChain，可调用轻量 mock 或 [A 的真实 ProteinMPNN 任务](docs/aiida_tasks.md)。WorkChain 使用 AiiDA 原生 `submit`、outline 等待和持久化上下文；推理与筛选参数分开输入，上游结果通过原生 `Dict` 端口连接。真实任务和仅重筛选的历史运行见 [R005 记录](experiments/R005-aiida-proteinmpnn/record.md)，整体进展见 [当前状态](docs/status.md)。

## 流程与公共端口

| 端口 | 方向 | 类型 | 用途 |
| --- | --- | --- | --- |
| `code` | 输入 | `AbstractCode` | 推理 Code；mock 声明 `ai4s.light-mpnn`，真实任务使用 `ai4s.proteinmpnn` |
| `pdb_file` | 输入 | `SinglefileData` | 上游结构 Data，按内容哈希与旧结果复核 |
| `mpnn_params` | 输入 | `Dict` | 只包含推理参数 |
| `filter_params` | 输入 | `Dict` | 只包含 `score_threshold` 和 `top_k` |
| `existing_mpnn_result` | 可选输入 | `Dict` | 旧复用入口；重筛选时直接沿用上游清单 Data |
| `request_id` | 可选输入 | `Str` | 约定②的引擎请求编号；与 `reuse_policy` 成对提供 |
| `reuse_policy` | 可选输入 | `Str` | `allow_reuse`／`force_rerun`／`new_sample` |
| `reuse_candidates` | 可选输入 | `List` | 按约定④登记候选；不合格项也保留原因 |
| `candidate_results` | 可选输入 | `Dict` | `<结果UUID>::<fingerprint>` 到结果节点 UUID 的映射 |
| `decision_function` | 可选输入 | `Str` | 可信的自定义决策器，格式为 `module:function` |
| `selected_sequences` | 输出 | `Dict` | 选中的样本及序列 |
| `sample_table` | 输出 | `Dict` | 选中样本、阈值和 `top_k` |
| `selection_report` | 输出 | `Dict` | 状态、复用决定、实际种子、尝试明细、启动计数和失败原因 |

WorkChain 的 outline 为：初始化（含复用决策） → 旧结果复用或按策略复用 → 有限推理尝试与等待 → 清单门禁 → 筛选。筛选输出由 `calcfunction` 创建并保留独立 creator；同一上游结果可以创建多个新的筛选过程。

## 环境准备

在个人 Coder 工作区使用已安装的 AiiDA 环境：

```bash
cd /home/coder/ai4s-workspace
source ~/.venvs/aiida/bin/activate
python -m pip install --no-deps -e .
chmod +x src/ai4s_workflows/bin/mock_mpnn.py
verdi daemon restart
```

首次启动可用 `verdi daemon start 1`。插件新增或代码修改后，需要刷新 editable 安装并重启本人 daemon，确保 worker 加载新模块；已有终止任务保留，另行提交新任务验证。不要操作其他成员的 daemon。

使用指向 `mock_mpnn.py` 的本人 `InstalledCode`，调用 `submit_workchain("mock-mpnn@localhost", threshold=1.08, top_k=2)`。mock 有 40% 的随机失败概率，仅用于观察重试，不能据此评价真实模型可靠性。mock Code 必须声明 `ai4s.light-mpnn`；真实 Code 未声明默认插件时回退到 `ai4s.proteinmpnn`。

## 真实任务提交

`submit_workchain()` 构造合成 PDB 和 mock 参数，只用于 mock。真实任务使用 builder：

```python
from aiida import load_profile, orm
from aiida.engine import submit
from ai4s_tasks.submit import DEFAULT_PDB
from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain

load_profile()
builder = ProteinMPNNFilterWorkChain.get_builder()
builder.code = orm.load_code("proteinmpnn-8907e667@localhost")
builder.pdb_file = orm.SinglefileData(file=DEFAULT_PDB)
builder.mpnn_params = orm.Dict(dict={
    "chains": "A", "num_sequences": 4,
    "sampling_temperature": 0.1, "seed": 41,
})
builder.filter_params = orm.Dict(dict={"score_threshold": 0.82, "top_k": 2})
builder.metadata.label = "proteinmpnn-filter-1crn-seed41"
node = submit(builder)
print(node.uuid)
```

提交成功不等于执行成功；用 `verdi process show <UUID>`、`verdi process report <UUID>` 和以下只读报告检查原生状态：

```bash
python -m ai4s_workflows.recovery --workchain <PK>
```

## 下游重算

成功 WorkChain 可用 `rerun_filter_only(node.pk, new_top_k=3, new_threshold=0.83)` 创建新的筛选过程。入口只复制并修改筛选参数，`code`、`pdb_file`、`mpnn_params` 和 `existing_mpnn_result` 继续引用原任务 Data：

```python
from ai4s_workflows.rerun import rerun_filter_only

rerun = rerun_filter_only(node.pk, new_top_k=3, new_threshold=0.83)
print(rerun.uuid)
```

验收时同时核对：新 WorkChain 的 `upstream_result_uuid` 与原任务一致；`attempt_count=0`、`model_launches=0`；新 WorkChain 的直接子节点中没有 CalcJob；mock 包装命令的启动计数文件未增加。`count_mpnn_launches()` 只统计 CalcJob 节点，不能替代外部程序启动计数，缓存命中时尤其如此。

## 复用策略与决策记录

新的复用链路要求同时提供 `request_id` 和 `reuse_policy`，并与旧 `existing_mpnn_result` 互斥。`allow_reuse` 选择第一条合格候选，无合格候选时用原参数、原种子重算；`force_rerun` 直接原种子重算；`new_sample` 生成不同有效种子。复用和重算都保留原种子，只有新采样改变 `effective_seed`。

```python
from aiida import orm

builder.request_id = "req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e"
builder.reuse_policy = "allow_reuse"
builder.reuse_candidates = orm.List(list=[candidate])
builder.candidate_results = orm.Dict(dict={
    f"{candidate['uuid']}::{candidate['fingerprint']}": candidate["uuid"],
})
# 可选：builder.decision_function = orm.Str("my_decisions:choose")
```

复用时 WorkChain 不创建 CalcJob，而是按 `candidate_results` 加载结果节点并通过相同的 schema／上游门禁；`selection_report.cached_from` 记录结果来源**过程** UUID，`selected_candidate_uuid` 记录结果节点 UUID。强制重跑和新采样会创建 CalcJob，并设置 `metadata.disable_cache=True`；新采样的 CalcJob 参数与报告使用同一个实际种子。

每次决定写入 WorkChain extras `ai4s_decision_records`，可按请求或过程 UUID 查询。完整字段、理由码、自定义决策器和 `208`／`209` 失败码见 [复用决策与决策记录](docs/reuse_decision.md)。

## 门禁、重试与失败记录

- 固定最多两次提交：一次首次尝试和一次重试（`MAX_ATTEMPTS=2`、`MAX_RETRY=1`）。
- 只有 CalcJob 成功、清单 schema 为 `ai4s-artifacts-1`、版本在白名单、`validation.passed is True`、无 `errors`／`issues`／`known_issues`、没有已知缓存失效标记，并且序列样本、文件端口和样本映射完整时，才进入筛选。
- 确定性门禁失败直接终止，不重新运行模型；CalcJob 失败或提交明确未产生外部作业时，最多再提交一次。
- `selection_report.attempts` 逐次保存 `attempt`、稳定 `label`、`calcjob_pk`／`calcjob_uuid`、`process_state`、`exit_status`、`cache_source` 以及提交前后 `model_launches`。失败报告另含 `status` 和可读 `reason`。
- 提交调用异常时，先按稳定 label 查询原生 CalcJob；查到外部作业或查询本身失败时返回 `SUBMISSION_STATE_UNCERTAIN`，不会盲目重复提交。人工核对通过后再决定恢复或重新提交。

常见失败状态包括 `failed_max_attempts`、`invalid_schema`、`invalid_manifest`、`missing_output`、`unsupported_version`、`unqualified_upstream` 和 `submission_uncertain`。`model_launches` 是已创建 CalcJob 的累计数，不是缓存命中时的外部模型启动次数。

故障样例：

| 状态 | 触发方式 | 预期 |
| --- | --- | --- |
| `failed_max_attempts` | mock 包装命令前两次均以 101 退出 | WorkChain 退出码 202，报告两条失败尝试和两个不同 CalcJob UUID |
| `invalid_manifest` | CalcJob 成功但清单 `validation.errors` 非空 | 不创建筛选输出，报告退出码 206 和原因 |
| `invalid_schema` | `existing_mpnn_result` 的 schema 不符 | 退出码 204，`model_launches=0` |
| `unqualified_upstream` | 上游 Data 的 Code／PDB／参数／文件映射与请求不一致 | 退出码 206，不进入筛选 |
| `submission_uncertain` | 提交调用异常且按 label 查到外部作业或核对查询失败 | 退出码 207，保留外部匹配身份，不自动重复提交 |

## daemon 停止与排队恢复

AiiDA WorkChain 的上下文和子过程状态保存在数据库中，正常停止并重启 daemon 后不应重新提交同一 WorkChain。操作顺序：

1. 先运行 `verdi daemon status`、`verdi process list -a`，记录 WorkChain 及子 CalcJob 的 PK、UUID、状态和退出码。
2. daemon 停止时提交的任务应保持 `waiting`；daemon 恢复后由 AiiDA 队列继续，不依据“没有输出”推断失败。
3. 正在执行的 direct 作业可能继续在操作系统层运行；daemon 恢复后先查原生状态和取回目录，再决定等待、`verdi process play <PK>` 或诊断失败。不要创建第二个相同作业。
4. 提交命令没有返回 UUID 或出现连接错误时，先按 attempt label 查询，例如 `python -m ai4s_workflows.recovery --label '<label>'`。只有确认没有外部作业且本次失败可安全重试时，才允许再次提交。
5. 将停止前后作业身份、状态和尝试日志写入运行记录；`selection_report.attempts` 与 `recovery.workflow_report()` 都可用于复核。

`tests/test_aiida_workflows.py` 在 POSIX 临时 profile 中包含排队 WorkChain 和运行中 WorkChain 的 daemon 停启恢复检查；这些检查涉及 daemon，Windows 主机直接跳过。

## 最小验证与原生验收

快速逻辑检查不需要 daemon：

```bash
PYTHONPATH=src python -m pytest -q \
  tests/test_reuse_decision.py \
  tests/test_workflow_logic.py \
  tests/test_ai4s_tasks.py
```

POSIX 目标环境运行完整 CPU mock 集成检查：

```bash
source ~/.venvs/aiida/bin/activate
python tests/test_aiida_workflows.py
```

测试使用独立临时 profile 和 daemon，覆盖成功两阶段、失败后重试、尝试上限、已知失效清单、异常子任务、仅重筛选、连续重算、稳定 label 核对、排队恢复和 daemon 停启恢复；不运行 GPU 模型。测试 wrapper 固定 mock 成功／失败次序，并保留每次真实包装命令的计数。

不依赖 C 辅助函数的原生验收示例：

```python
from aiida import load_profile, orm

load_profile()
workchain = orm.load_node(<WORKCHAIN_PK>)
print(workchain.uuid, workchain.process_state, workchain.exit_status)
print(workchain.outputs.selection_report.get_dict())
for child in workchain.called:
    print(child.pk, child.uuid, child.process_type, child.process_state, child.exit_status)
for child in workchain.called:
    if isinstance(child, orm.CalcJobNode):
        print("calcjob input result:", child.inputs.params.uuid)
```

返回：[A 模块](docs/aiida_tasks.md) · [复用决策](docs/reuse_decision.md) · [运行记录](experiments/R005-aiida-proteinmpnn/record.md) · [当前状态](docs/status.md) · [仓库](README.md)。
