# R005：AiiDA ProteinMPNN 接入与两阶段最小验证

状态：2026-11-05 的四次历史运行和 2026-11-11 的真实 GPU 三种复用策略复验均已完成；2026-11-13 又完成 fork 内核接入的 CPU mock 隔离验证。各部分分别保留当时的环境和身份，旧运行不能替代新链路证据。目标是验证真实任务接入、单任务缓存、局部重算和复用决策记录，不评价蛋白质功能或模型优劣。入口：[A 模块](../../docs/aiida_tasks.md)、[C 模块](../../README_C.md)、[当前状态](../../docs/status.md)。

## 代码与执行环境

| 项目 | 实际身份／位置 |
| --- | --- |
| 对应 PR | [#9](https://github.com/QUHONGYE-gif/ai4s-workspace/pull/9)，`dev-qhy@9796bde1c364325455ad7a5a3491e1bea7c6d25e` |
| A 的引入提交 | `186a889605d39fc93dc4a7d47d5f7a5089062eb9` |
| 执行位置 | 项目科研服务器的 qhy 个人 Coder 容器；代码目录 `/home/coder/ai4s-workspace` |
| AiiDA | `aiida-core 2.9.4`、Python `3.12.15`；个人 `ai4s` profile、`localhost` Computer |
| AiiDA 环境 | `/home/coder/.venvs/aiida`，共享版本 `2.9.4-py312` |
| Code | `proteinmpnn-8907e667@localhost`；UUID `6bdfbe2f-ed50-421e-aff1-1fa7459dcaaa` |
| 实际可执行文件 | `/opt/ai4s/proteinmpnn/bin/proteinmpnn`；该 Code 未设默认插件，单任务显式选择 `ai4s.proteinmpnn`，C 使用真实任务回退值 |
| 模型 release | `8907e667-py312-torch260cu124`；上游提交 `8907e6671bfbfc92303b5f79c4b5e6ce47cdef57` |
| 输入 | 共享 release 的 `examples/1CRN.pdb`，链 A；SHA-256 `42199a30a0701864a2a5cc76cd7f35cc544cd0e65fbcf63e03c166543249b811` |
| 权重 | `v_48_020`；运行记录中的 SHA-256 `c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd` |

服务器回查时仓库 HEAD 仍为 `f8b3e43b1faa8ad7b0026b26039b78fdb866e68f`，A/C 源码是未跟踪部署文件，不能仅凭该 HEAD 代表运行代码。补文档时将 `src/ai4s_tasks/*.py` 的 4 个文件及 C 的 `workflows.py`、`filtering.py`、`rerun.py`、`samples.py` 与 PR 上述提交逐文件比较 SHA-256，全部一致。核心文件摘要如下：

```text
22f09632393f4005dacf3f93007499699f420b02123ae2931641e3f089a63fe6  src/ai4s_tasks/proteinmpnn.py
0ca641b5ccee3ff2710db2ab4703842c7cf3349c03b7e2384f02481fd35d2cef  src/ai4s_tasks/proteinmpnn_outputs.py
206a060bda09e4034931b297ed5c958b93d20940ab732a3d5f68341fa3ded8a2  src/ai4s_workflows/workflows.py
d0e155fc4834d6ae4d3f03912c45bc74174e97c436a3a1ac3857b3217fbbcc7b  src/ai4s_workflows/filtering.py
```

该比对证明回查时部署文件与 PR 一致，不是任务创建时自动留存的全环境快照。PR 原记录报告单卡 GPU 最小运行；本次仅回查数据库、产物和源码，没有重新验收设备分配或测量性能。

## 已完成运行

以下 PK 仅在上述个人 profile 有效，对外识别使用 UUID；四个过程均为 `Finished [0]`。

| 场景 | PK／UUID | 参数与结果 |
| --- | --- | --- |
| 真实单任务 | 22 / `b8b0e7d0-f1e3-4f98-8bee-454b5010b98c` | seed=37；4 条设计序列；正式序列、分数、概率和通过校验的清单均存在；无缓存来源 |
| 单任务缓存 | 31 / `7550be4d-0bdc-45e8-9c5d-14c61151788c` | 相同内容与参数；原生缓存来源为 pk 22 UUID，不能将复制的运行时间或远程目录解释为第二次执行 |
| 真实两阶段 | 41 / `3dc38915-aaa1-4e27-b0cf-67ded3ace293` | seed=41；阈值 0.82、top_k=2；选中 s004(0.7703)、s003(0.7794) |
| 仅重筛选 | 55 / `671346a8-bedd-4f2a-baa3-e8273edb1d8e` | 阈值 0.83、top_k=3；选中 s004、s003、s001(0.8031)；旧结果保留 |

共同推理配置为链 A、温度 0.1、`num_sequences=4`、`batch_size=1`、`model_name=v_48_020`、`save_probabilities=True`。pk 41 的输入只显式保存前四个必需参数，后三项由 A 的默认值展开。

pk 22 包装命令的实际起止为 2026-11-05 21:19:28–21:20:06（Asia/Taipei，原始记录为 UTC）；pk 42 为 21:26:51–21:27:09。时间仅描述这两次运行，不用于性能结论。

pk 41 的子过程为：

- ProteinMPNN CalcJob：pk 42 / `e2c47644-9cbb-4ff0-936b-3f7c4e3e157b`，无缓存来源。
- 筛选 calcfunction：pk 50 / `274fb864-ab75-434b-9b15-b35d59cbb8d2`。
- 筛选报告：`model_launches=1`、`retry_attempt=0`、`mpnn_cache_source=null`、`selected_count=2`。

pk 55 通过 `existing_mpnn_result` 使用原上游 Data `2f67a2f2-8d5c-4cd6-b1e0-2d1bf2bb1515`，只调用筛选 pk 57 / `b7a702f9-6bf7-4349-ab96-d8200183c4e8`，无新 CalcJob，报告 `model_launches=0`、`selected_count=3`。这是直接复用旧 Data 的下游重算，与 pk 31 的计算缓存命中不同。结合新流程的实际调用链接判断未增加推理，不单靠计数辅助函数的返回值判断。

## 命令与产物回查

模块安装、独立提交及真实 WorkChain 的可运行命令分别维护在 A、C 说明中。以下是 pk 22 保存的 `_aiidasubmit.sh` 中实际模型命令；工作目录是 AiiDA 独立任务目录，不应在原目录再次手工执行：

```bash
/opt/ai4s/proteinmpnn/bin/proteinmpnn \
  --pdb_path input.pdb --pdb_path_chains A \
  --num_seq_per_target 4 --batch_size 1 --sampling_temp 0.1 \
  --seed 37 --model_name v_48_020 --save_score 1 --save_probs 1 \
  --out_folder outputs > aiida.out
```

下面的只读命令用于在原 profile 回查，非新实验提交：

```bash
source ~/.venvs/aiida/bin/activate
verdi process show b8b0e7d0-f1e3-4f98-8bee-454b5010b98c
verdi process show 3dc38915-aaa1-4e27-b0cf-67ded3ace293
verdi process report 3dc38915-aaa1-4e27-b0cf-67ded3ace293
verdi process show 671346a8-bedd-4f2a-baa3-e8273edb1d8e
python - <<'PY'
from aiida import load_profile, orm
load_profile("ai4s")
cached = orm.load_node("7550be4d-0bdc-45e8-9c5d-14c61151788c")
print("cached_from:", cached.base.caching.get_cache_source())
calc = orm.load_node("b8b0e7d0-f1e3-4f98-8bee-454b5010b98c")
print(calc.outputs.result.get_dict())
print(calc.outputs.retrieved.base.repository.get_object_content("outputs/run.json"))
for pk in (41, 55):
    node = orm.load_node(pk)
    print(node.uuid, node.outputs.selection_report.get_dict())
    print([(child.uuid, child.process_label) for child in node.called])
PY
```

pk 22 的取回节点为 `78f6788d-c599-43b9-8c9f-9f83fab385e2`，含 `outputs/run.json`、`outputs/run.log`、`outputs/seqs/input.fa`、`outputs/scores/input.npz`、`outputs/probs/input.npz`、`aiida.out` 和调度日志。正式文件分别为：

| 输出 | Data UUID |
| --- | --- |
| `artifacts.sequences` | `866433ea-5f1a-450d-ad99-8fed21efeaec` |
| `artifacts.scores` | `dc6b9576-f08b-4e1c-8077-a2b41993d391` |
| `artifacts.probabilities` | `ca68e07b-fc4d-45b5-988e-cf3f755fea7c` |
| `result` | `d36e4209-4386-4452-925c-bbf9a5b51126` |

原始任务目录为 `/home/coder/.local/share/aiida/work/b8/b0/e7d0-f1e3-4f98-8bee-454b5010b98c`；持久化取回内容以节点 Repository 为准。数据保存在个人 profile 和 home 卷中，本记录不复制模型、权重、Repository 或大型输出。

## 检查与未验证范围

- 本次文档补充前重新运行 `PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/envs/lab/bin/python -m pytest -q tests/test_ai4s_tasks.py`，4 项通过；仅覆盖参数、FASTA 和分数辅助函数，不是完整 Parser 集成测试。
- PR 原有记录报告：目标服务器直接调用四个辅助测试函数通过，`python tests/test_aiida_workflows.py` 在独立临时 profile 的 7 项 CPU mock 检查通过。本次未重跑该组，也未把它当作真实 GPU 或 daemon 中断恢复的证据。
- 2026-11-05 记录对应的运行未覆盖真实 WorkChain 缓存命中、daemon 停启恢复、B 的真实产物查询、多成员／跨 profile 访问、完整缓存失效条件和正式网页提交；2026-11-11 的真实三种复用策略复验见后文，其余各项仍未由本次复验覆盖。
- 权重哈希仅被记录；完整运行身份、概率数值及样本映射、异常文件诊断和正式端口差异的实现边界见模块说明。记录时源码仍为三次提交上限，后续已改为最多两次尝试，见下一节。

## 2026-11-08 后续源码变更（未重跑）

C 模块之后将提交上限改为最多两次尝试，并加入逐次尝试明细、稳定 label 提交核对、已知失效清单门禁、原生恢复报告和 daemon 排队／停启检查。上述源码变更后的运行记录不能沿用本页旧 PK 冒充；已有真实两阶段与仅重筛选仍只对应本页旧源码版本。新变更的快速逻辑检查和 Linux CPU mock 集成检查已通过；2026-11-11 当前个人 profile 中的真实三种复用策略复验见下一节。

## 2026-11-11 真实 GPU 三种复用策略复验

本节记录 2026-11-11 在当前个人 `ai4s` profile 上对新复用决策与记录链路的真实执行事实。上文 PK 22／31／41／55 属于更早环境和来源版本，不能与本节的 PK 74／94／107 混用。

| 策略 | WorkChain | 决策／理由码 | 实际种子 | 模型启动 | CalcJob／结果 |
| --- | --- | --- | ---: | ---: | --- |
| `allow_reuse` | PK 94 / `599e385a-cb5a-4de7-9180-0ffdde836a8f` | `reuse` / `R01` | 41 | 0 | 无 CalcJob；复用结果 `87ada36e-8a31-4805-b5f8-52813d27219f` |
| `force_rerun` | PK 74 / `89fea7d1-1fdd-41c8-904d-788b674ab888` | `rerun` / `R03` | 41 | 1 | CalcJob PK 75 / `77f45c98-8471-4f88-8034-1e0198b3e0e7` |
| `new_sample` | PK 107 / `439c5913-830e-4f60-b05f-3895185cbd57` | `new_sample` / `R04` | 3491716553 | 1 | CalcJob PK 109 / `1197e36a-0afc-4d5d-a851-299c33e8f988` |

公共执行条件：

| 项目 | 实际数据 |
| --- | --- |
| AiiDA | `aiida-core 2.9.4`，`ai4s` profile，daemon 单 worker |
| Code | `proteinmpnn-8907e667@localhost`，PK 57，UUID `037c05e5-9f42-470b-8df8-03d7e61ec386` |
| 输入 | release `8907e667-py312-torch260cu124` 的 `examples/1CRN.pdb`，链 A |
| 参数 | `num_sequences=4`、温度 0.1、原种子 41、阈值 0.82、`top_k=2` |
| 单任务证据 | CalcJob PK 60 / `9e6d9350-f564-465b-90b6-07178e12535b`，`Finished [0]`，无缓存来源 |

### `force_rerun`

- 请求编号：`req-a8ae5d84-430a-44c8-88d1-6a35b7eaf4a2`
- 决策：`force_rerun` → `rerun`，`R03`，`effective_seed=41`
- 启动计数：`model_launches=1`、`attempt_count=1`、`retry_attempt=0`
- 筛选：`selected_count=2`，`selection_report` PK 86
- 上游结果 UUID：`87ada36e-8a31-4805-b5f8-52813d27219f`

`verdi process report 74` 依次记录复用决策、唯一一次 MPNN 提交和筛选完成，没有错误或重试。Recovery 返回 WorkChain 和 CalcJob 均为 `finished`、退出码 0，CalcJob 的 `cache_source` 为 `null`。决策记录可按 `request_id` 查回：

```text
reuse_policy: force_rerun
action: rerun
effective_seed: 41
reason_code: R03
```

### `allow_reuse`

- 请求编号：`req-67946afc-bc54-4ee6-a09c-c3ddd93cd695`
- 候选结果 UUID：`87ada36e-8a31-4805-b5f8-52813d27219f`
- 候选 fingerprint：`fb62f09bd450f8fe`
- 结果来源过程：CalcJob PK 75 / `77f45c98-8471-4f88-8034-1e0198b3e0e7`
- 决策：`allow_reuse` → `reuse`，`R01`，`effective_seed=41`
- 启动计数：`model_launches=0`、`attempt_count=0`、`calcjob_submissions=0`
- WorkChain PK 94 下没有 CalcJob；`selected_candidate_uuid` 为结果节点 UUID，`cached_from` 为来源过程 UUID
- 筛选：`selected_count=2`
- 决策记录可按 `request_id` 查回 R01

### `new_sample`

- 请求编号：`req-2e5db5c5-e75b-4fac-9942-3c59cbb85bea`
- 决策：`new_sample` → `new_sample`，`R04`，`effective_seed=3491716553`
- 启动计数：`model_launches=1`、`attempt_count=1`、`calcjob_submissions=1`
- 实际 CalcJob PK 109 的参数种子与 `selection_report.effective_seed` 均为 `3491716553`
- CalcJob PK 109 为 `Finished [0]`，`cache_source=null`
- 筛选：`selected_count=2`，新结果 UUID 为 `76055eb8-9201-4ff5-9e5e-eeabe42a98c7`
- `ai4s_decision_records` 按 `request_id` 仅返回一条 R04 记录，决策中的 `effective_seed` 与实际 CalcJob 一致

```text
request_id: req-2e5db5c5-e75b-4fac-9942-3c59cbb85bea
process_uuid: 439c5913-830e-4f60-b05f-3895185cbd57
reuse_policy: new_sample
action: new_sample
effective_seed: 3491716553
reason_code: R04
```

这次复验证明当前个人 profile 中的真实 ProteinMPNN CalcJob、两阶段筛选、三种复用策略和 `ai4s_decision_records` 查询均可用。`allow_reuse` 复用同一 profile 中由 PK 75 产生的真实结果候选，不是跨成员或跨 profile 共享证据。本次没有证明网页实时回显、真实 daemon 中断恢复或团队共享 profile；这些边界仍需后续联调。该次运行发生在此次 fork 内核接入之前，不能替代接入后的真实 GPU 复验。

## 2026-11-13 AiiDA 内核接入隔离验证（CPU mock）

本轮只验证项目 WorkChain 与团队 AiiDA fork 的接入和自动化测试，不运行真实 GPU 模型，也不修改共享 `ai4s` profile。fork 仓库为 `https://github.com/WuYuhui01/aiida-core.git`，分支 `dev-wyh`，验证提交 `9a1e474f2`；使用独立环境 `~/.venvs/aiida-reuse` 和临时 profile。

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 主项目 CPU mock 集成 | `python tests/test_aiida_workflows.py` | `Ran 15 tests`，`OK` |
| fork 复用内核 | `python -m pytest -q -o addopts='' --broker-backend=zmq tests/engine/test_reuse.py` | `15 passed` |

主项目检查覆盖三种复用策略、实际种子与启动次数、候选注入、决策记录、daemon 停止／重启恢复、重试上限、无效清单和 schema 门禁；fork 检查覆盖受控决策、跨类型候选结果消费、原生缓存边界和用户策略约束。默认 RabbitMQ 后端未配置，因此 fork 测试使用 ZeroMQ。

本轮证明接入代码在隔离 CPU mock 环境中可用，不代表 fork 接入后的真实 GPU 三策略、网页实时回显、共享 profile、跨成员复用或真实 daemon 恢复已经验收。

返回：[A 模块](../../docs/aiida_tasks.md) · [C 模块](../../README_C.md) · [当前状态](../../docs/status.md) · [仓库](../../README.md)。
