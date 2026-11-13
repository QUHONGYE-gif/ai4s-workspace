# A 模块：ProteinMPNN 单任务接入

本模块通过 AiiDA 原生 CalcJob 和 Parser 调用已部署的 ProteinMPNN，提供独立提交、输出校验和产物节点；与 C 的组合方式见 [工作流说明](../README_C.md)，复用内核接入见 [复用决策](reuse_decision.md)，已有执行证据见 [运行记录](../experiments/R005-aiida-proteinmpnn/record.md)。当前进展见 [状态](status.md)。

## 环境与入口

在已配置共享 AiiDA、个人 profile 和 ProteinMPNN 的 Coder 工作区执行：

```bash
cd /home/coder/ai4s-workspace
source ~/.venvs/aiida/bin/activate
python -m pip install --no-deps -e .
verdi status
verdi plugin list aiida.calculations ai4s.proteinmpnn
verdi plugin list aiida.parsers ai4s.proteinmpnn
```

`aiida-core` 与 NumPy 由现有 AiiDA 环境提供，不通过工作台的 `uv.lock` 安装。通用依赖与个人配置规则见 [运行要求](environment.md)。安装或更新插件后，在本人无运行任务时启动或重启本人 daemon，使其加载相同源码；不要操作其他成员的 daemon。

本轮 fork 内核接入验证使用独立环境 `~/.venvs/aiida-reuse` 和临时 profile，未修改共享的个人 `ai4s` profile；fork 地址、提交和测试命令见 [C 模块的内核验证说明](../README_C.md#aiida-内核复用接入与隔离验证)。

本人 profile 还需存在 `localhost` Computer（本地传输、direct 调度），以及以下 Code。首次注册前先用 `verdi code list` 核对，已有 Code 不重复创建：

```bash
python - <<'PY'
from aiida import load_profile, orm
load_profile()
code = orm.InstalledCode(
    label="proteinmpnn-8907e667",
    computer=orm.load_computer("localhost"),
    filepath_executable="/usr/local/bin/proteinmpnn",
    default_calc_job_plugin="ai4s.proteinmpnn",
)
code.store()
print(code.uuid)
PY
```

示例路径适用于已部署的个人工作区；其他环境需替换 Code 可执行路径和 PDB 路径。默认 PDB 是共享版本目录中的真实 1CRN，不是 `tests/fixtures/backbone.pdb` 合成样例。

```bash
# 前台执行并等待结束；也可加 --submit 交给本人 daemon。
python -m ai4s_tasks.submit --seed 37
# 异步提交后以原生状态判断是否完成，提交成功不等于执行成功。
python -m ai4s_tasks.submit --seed 41 --submit
verdi process show <UUID>
verdi process report <UUID>
```

两条命令分别提交任务，按实际需要选择一条。默认 Code 是 `proteinmpnn-8907e667@localhost`；`--pdb`、`--code` 可覆盖。完整参数见 `python -m ai4s_tasks.submit --help`。

## 实际接口

源码：[执行与解析](../src/ai4s_tasks/proteinmpnn.py)、[参数与文件检查](../src/ai4s_tasks/proteinmpnn_outputs.py)、[提交入口](../src/ai4s_tasks/submit.py)。

| 输入 | 内容 |
| --- | --- |
| `code` | 指向共享 `proteinmpnn` 包装命令的原生 Code |
| `pdb_file` | 原生 `SinglefileData`，执行时复制为 `input.pdb` |
| `params` | `Dict`；必填 `chains`、`num_sequences`、`sampling_temperature`、非零 `seed` |
| 可选参数 | `model_name=v_48_020`、`batch_size=1`、`save_probabilities=True` |

序列数和 batch_size 要求正整数且整除，温度是单个正数。首轮验证范围为单链、单温度、4 条设计序列；其他输入范围不能由参数存在推定为已验证。

| 输出 | 类型与含义 |
| --- | --- |
| `result` | `Dict`，含 `ai4s-artifacts-1` 清单、样本序列及分数、原生序列、运行身份和校验结论 |
| `artifacts.sequences` | `SinglefileData`，`design.fa`，保留原生记录与设计记录 |
| `artifacts.scores` | `SinglefileData`，`scores.npz`，与设计记录逐条对应 |
| `artifacts.probabilities` | 请求时提供的 `SinglefileData`，`probabilities.npz` |
| `retrieved` | 原生取回目录，保存 `aiida.out`、`outputs/run.json`、`outputs/run.log` 及所请求的嵌套产物 |

`result` 同时承担清单和内联运行记录，当前没有单独的 `artifact_manifest`、`execution_report` 端口。C 的筛选按 `artifacts.sequences` 端口查找并读取清单中的内联样本，尚未直接消费 `artifacts.sequences/scores` 文件节点；这是当前实现与完整接口规划的差异。

## 校验与失败

Parser 依次检查包装命令成功结束、固定 release、输入 PDB SHA-256 与输入节点一致、权重文件名符合 model_name、实际种子符合请求，再检查必需输出、设计数量与长度、种子／模型名／温度、FASTA 与 NPZ 分数的一致性，以及请求概率数组的 `(设计数, 残基数, 21)` 形状、有限数值、[0, 1] 范围和归一化。概率文件的 `S` 与 `chain_order` 还需按 FASTA 样本编号和链顺序对应；链分隔符不计入残基数。原生序列不计入设计数量；分数比较容差为 `1e-4`。

上述检查全部通过后才发布正式文件和 `result`。显式失败码 300–308 对应运行记录缺失、模型失败、版本不符、输入不符、输出缺失、设计不符、分数不符、概率内容不符及输出损坏，均标记 `invalidates_cache=True`。损坏 JSON／NPZ 或缺失内部字段返回 308，清单先构造成功才发布任何正式输出。

权重 SHA-256 和上游源码提交由包装命令记录并写入清单；当前 Parser 只核对权重路径后缀及 release，没有与预先固定的权重哈希／源码提交比较。数值与样本映射规则通过了合成文件检查，并对既有真实任务 pk22 的取回产物作了只读复核，新 Parser 通过且数据库节点数未变化。本轮没有重新执行 GPU 模型，不构成新版本 GPU 全流程验收。

## 缓存与能力边界

单任务已有一次原生缓存命中证据，见运行记录。可在受控环境中显式使用 `aiida.manage.caching.enable_caching` 测试，默认是否启用以当前 profile 配置为准。`model_launches` 与 CalcJob 节点数不是外部程序实际启动次数，尤其要排除缓存命中。

当前没有统一 `reuse/recompute/new_sample` 请求接口、旧输出重新解析入口或 checkpoint 恢复。权重与环境身份保存在执行后记录中，未完整进入稳定的计算输入；若共享程序、权重或环境改变，不应直接沿用旧缓存，应禁用缓存并重新验证部署身份。不要将本次命中推广为完整的缓存失效条件验收。

六项轻量检查覆盖参数、FASTA、分数和概率内容／样本对应；NumPy 来自 AiiDA 环境：

```bash
PYTHONPATH=src python -m pytest -q tests/test_ai4s_tasks.py
```

CalcJob 与 Parser 的 `CACHE_VERSION` 均已提升为 2，清单的 `validator_version` 为 `proteinmpnn-2`。旧规则的缓存不会与新规则直接匹配；C 也拒绝直接消费旧验证版本的真实结果。旧过程与输出继续保留，当前没有把旧结果重新解析为新版本的公共入口。

`python tests/test_aiida_workflows.py` 在独立临时 profile 检查实际 Parser 的合成损坏文件、C 的两次提交上限、逐次尝试日志、daemon 排队／停启恢复与连续重筛选，以及 B 的 ORM 查询与只读导出；不运行模型。该脚本要求 POSIX daemon，Windows 开发机直接跳过。真实 GPU 恢复、新版本全流程和网页提交仍需在目标环境分别验证。上述实现不等于两个任务已共用一个通用 CalcJob／Parser，筛选目前是 C 的 `calcfunction`。新增快速逻辑检查见 [C 模块说明](../README_C.md#最小验证与原生验收)。

返回：[C 模块](../README_C.md) · [运行记录](../experiments/R005-aiida-proteinmpnn/record.md) · [当前状态](status.md) · [仓库](../README.md)。
