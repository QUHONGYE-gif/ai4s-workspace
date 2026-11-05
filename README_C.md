# C模块：编排、重算与恢复

当前提供推理 CalcJob → 产物门禁 → 筛选 calcfunction 的两阶段 WorkChain，可调用轻量 mock 或 [A 的真实 ProteinMPNN 任务](docs/aiida_tasks.md)。真实任务、单任务缓存及仅重筛选已有 [运行记录](experiments/R005-aiida-proteinmpnn/record.md)；daemon 中断恢复尚未验收。整体进展见 [当前状态](docs/status.md)。

## 环境准备

在个人 Coder 工作区使用已安装的 AiiDA 环境：

```bash
cd /home/coder/ai4s-workspace
source ~/.venvs/aiida/bin/activate
python -m pip install --no-deps -e .
chmod +x src/ai4s_workflows/bin/mock_mpnn.py
verdi daemon restart
```

首次启动可用 `verdi daemon start 1`。插件新增或代码修改后，需要刷新 editable 安装并重启本人 daemon，确保 worker 加载新模块；已有终止任务保留，另行提交新任务验证。

使用指向 `mock_mpnn.py` 的本人 `InstalledCode`，调用 `submit_workchain("mock-mpnn@localhost", threshold=1.08, top_k=2)`。mock 有 40% 的随机失败概率，用于手动观察重试，不能据此评价真实模型的可靠性。

mock 的计算／解析器入口为 `ai4s.light-mpnn`，真实任务的计算／解析器入口为 `ai4s.proteinmpnn`，工作流入口为 `ai4s.protein-mpnn-filter`；入口名不包含分组前缀或冒号。WorkChain 优先使用 Code 的 `default_calc_job_plugin`，未声明时默认 `ai4s.proteinmpnn`，因此 mock Code 必须明确声明 `ai4s.light-mpnn`。

## 真实任务提交与重筛选

`submit_workchain()` 仍构造合成 PDB 和 mock 参数，只用于 mock。真实任务使用下面的 builder，不能只替换该函数的 Code 名称：

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
node = submit(builder)
print(node.uuid)
```

在相同 Python 环境和 profile 中检查 `verdi process show <UUID>`、`verdi process report <UUID>`。成功后可用 `rerun_filter_only(node.pk, new_top_k=3, new_threshold=0.83)` 提交新 WorkChain；该调用需要先导入 `from ai4s_workflows.rerun import rerun_filter_only`。`node.pk` 应替换为本人已成功完成的原流程 PK，不可套用其他 profile 的编号。

## 执行与结果

- `LightMPNNCalcJob` 用 `SandboxFolder.open()` 写入 `params.json` 和 `input.pdb`，取回 `result.json`。
- `LightMPNNParser` 将取回文件解析为 `result: Dict`；缺失结果返回 101，非法 JSON 返回 102。
- WorkChain 仅在 `is_finished_ok` 时读取结果；`Excepted`、`Killed` 和非零退出均进入有限重试。两次重试表示总计最多三次提交。
- 新结果与复用结果都检查 schema、产物列表和支持版本。筛选通过 `calcfunction` 创建输出，保留输入依赖及 creator；输出仍为 `selected_sequences`、`sample_table`、`selection_report`。
- 真实任务先由 A 校验文件并发布 `result`；C 的门禁目前只检查 schema、非空产物列表与版本白名单，没有独立复核 `validation.passed`、必需文件端口及复用计算身份。不要直接把任意外来 Dict 当作可信上游。
- 筛选消费 `result.artifacts[0].samples`，使用 `score` ≤ 阈值，按 `(score, sample_id)` 升序取前 `top_k` 条。三个输出均为 `Dict`，没有生成筛选 FASTA，也尚未采用 `artifacts.*` 输出命名空间。
- `rerun_filter_only(old_wc_pk, ...)` 复用原任务的上游 `result`，不再次提交 MPNN。builder 中的 code、pdb_file、mpnn_params 用于满足输入声明；筛选阶段不执行它们。
- `selection_report.mpnn_cache_source` 表示本次子 CalcJob 的缓存来源；重筛选没有提交该子任务，因此该字段为空，应通过 `existing_mpnn_result` 的原生输入链接追溯。`model_launches` 累加的是子 CalcJob 提交数，`count_mpnn_launches()` 统计的是 CalcJob 节点数；两者均不能直接等同于缓存场景下的外部程序启动次数。

当前 `MAX_RETRY=2` 表示两次重试、最多三次提交，与飞书本轮“最多两次尝试”的要求尚未对齐。本文记录实际行为，不更改实现或替代接口决策。checkpoint 续跑和实际 daemon 停启恢复均未验证。

## 最小验证

```bash
source ~/.venvs/aiida/bin/activate
python tests/test_aiida_workflows.py
```

测试会创建独立临时 profile 和 daemon，使用 CPU mock 验证文件输入、Parser、筛选输出来源、一次失败后的重试、重试上限、异常子任务和仅重筛选。测试 wrapper 固定 mock 的成功或失败次序，保留手算预期样本 `s001/s002`；结束后停止测试 daemon，不使用本人现有 profile。普通 pytest 收集会跳过此独立集成测试。

返回：[A 模块](docs/aiida_tasks.md) · [运行记录](experiments/R005-aiida-proteinmpnn/record.md) · [当前状态](docs/status.md) · [仓库](README.md)。
