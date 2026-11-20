# R008：成本决策真实验收

状态：已通过。基于真实 Coder／AiiDA Profile 和真实 CPU ProteinMPNN 形成最终证据，六项硬性检查全部为真。本轮只推送个人分支 `dev-wyh`，不直接推送或合并 `main`，也不评价蛋白质功能或模型质量。

## 范围与运行身份

- 日期：2026-11-18。执行源码来自 `dev-wyh` 工作区，基线为 `e9ddf3feaf297392eb070f761d950bb665afe153`；成本决策实现随后提交并推送至 `dev-wyh`。运行快照位于 `/home/coder/runs/cost-decision-20261118/snapshot`；之后只整理文档，不改写本次结果。
- AiiDA：`2.9.4`；真实 Profile：`ai4s-wyh-reuse`；执行位置：个人 Coder 工作区。
- Code：`proteinmpnn-8907e667@localhost`，UUID `fa81bdf7-1832-4a7a-88ca-bd6ddb27037e`，PK `1`，插件 `ai4s.proteinmpnn`。
- 输入：`/opt/ai4s/proteinmpnn/releases/8907e667-py312-torch260cu124/examples/1CRN.pdb`，SHA-256 `42199a30a0701864a2a5cc76cd7f35cc544cd0e65fbcf63e03c166543249b811`。
- ProteinMPNN 参数：A 链、4 条序列、`batch_size=1`、温度 `0.1`、种子 `41`、模型 `v_48_020`、保存概率。筛选参数：阈值 `10.0`、`top_k=2`。
- 运行类型：真实 CPU ProteinMPNN；不是 mock、dry-run、离线单元测试或历史结果重放。
- 策略文件：`/home/coder/runs/cost-decision-20261118/cost-policy.json`。低固定开销策略使用 `0.5s` 固定开销、`1048576B/s` 带宽、`0.2s` 物化、`1s` 最小节省；高固定开销策略使用 `60s` 固定开销、`0s` 物化、`1s` 最小节省。
- 输入与数据标识：来源候选 UUID `aae215ce-3796-4e9c-bbd6-6455cf104c08`，指纹 `25aac783f44c1a96fccffd04177746d9d77818e035ed1519fc14ea182285af5a`。来源候选实测墙钟 `49.9s`，正式产物未压缩总大小 `34287B`。

## 命令

目录和绝对路径来自本次运行。首次任务在 `real-run-2.json` 中完成前五个真实阶段；修正无效 PDB 的绝对路径后，从原生 UUID 续跑并生成最终证据：

```bash
cd /home/coder/runs/cost-decision-20261118/snapshot
python scripts/verify_cost_decision_real.py \
  --output /home/coder/runs/cost-decision-20261118/evidence/real-run-2.json \
  --policy-file /home/coder/runs/cost-decision-20261118/cost-policy.json

python scripts/verify_cost_decision_real.py \
  --output /home/coder/runs/cost-decision-20261118/evidence/real-run-3.json \
  --policy-file /home/coder/runs/cost-decision-20261118/cost-policy.json \
  --resume-from /home/coder/runs/cost-decision-20261118/evidence/real-run-2.json
```

验证脚本不只是读取旧 JSON：续跑时会按 AiiDA UUID 重新加载已完成阶段，重新执行 `build_candidate`，核对 UUID、指纹、资格、缓存标记、耗时、大小和原生子过程。每个阶段都等待 WorkChain／CalcJob 原生终态；输出文件已存在时拒绝覆盖。

## 真实验证结果

| 阶段 | 原生过程 | 决定／理由 | 种子 | CalcJob／模型执行 | 关键结果 |
| --- | --- | --- | ---: | ---: | --- |
| 真实来源 | WorkChain 63／CalcJob 64 | R03 强制重算 | 41 | 1／1 | 实测 `49.9s`、`34287B`，候选未缓存 |
| 默认复用 | WorkChain 83 | R01 复用 | 41 | 0／0 | 选中来源候选，没有创建 CalcJob |
| 成本判断复用 | WorkChain 96 | R05 复用 | 41 | 0／0 | 预计重算 `49.900s`、复用 `0.733s`、节省 `49.167s` |
| 成本判断重算 | WorkChain 109／CalcJob 110 | R05 重算 | 41 | 1／1 | 固定开销 `60s`，复用预计 `60.033s`，节省 `-10.133s` |
| 新采样 | WorkChain 128／CalcJob 129 | R04 新采样 | `1035027373` | 1／1 | 新种子不同于 41，真实计算一次 |
| 失败候选 | CalcJob 143 | 原生失败 | 41 | 1／1 | `exit_status=301`，候选 `qualified=false`，理由以 `not_finished:` 开头 |
| 失败候选排除 | WorkChain 154／CalcJob 155 | R05 安全重算 | 41 | 1／1 | 失败候选仍在比较列表且不合格，未复用，安全重算一次 |

所有成功来源、成本重算、新采样和失败排除重算的 CalcJob `cache_source` 均为 `None`；没有把 AiiDA 原生缓存命中误报成新模型执行。

六项硬性检查全部通过：

```json
{
  "source_is_real_measured": true,
  "default_reuse_R01_no_calc": true,
  "cost_reuse_R05_no_calc": true,
  "cost_rerun_R05_one_calc": true,
  "new_sample_R04_new_seed_one_calc": true,
  "failed_candidate_excluded_and_safe_rerun": true
}
```

## 证据

- 最终证据：[real-run-3.json](evidence/real-run-3.json)，SHA-256 `5d4ba067d8342620c2c29c784f42229015f89497e60e1a1e5718707dd37711c6`，`status=passed`。
- 最终运行日志：[run-3.log](evidence/run-3.log)。文件为空是正常的；脚本仅在出现错误时写入日志。
- 无效输入：[invalid-input.pdb](evidence/invalid-input.pdb)。
- 验证脚本：[verify_cost_decision_real.py](../../scripts/verify_cost_decision_real.py)，SHA-256 `0539a98a2875f9544b158308749fce13ba66cae3b2e6a18ae95bf966fb59d91e`。
- 说明与展示入口：[成本决策说明](../../docs/cost_decision.md) · [投屏页面](../../docs/cost_decision_visual.html) · [演示讲稿](../../docs/cost_decision_speech.md)。

验收提交 `0ca663d` 的关键源码 SHA-256（运行使用外部 snapshot，以下哈希用于核对仓库内容）：

```text
9e769e03a5816435ee00e3ea1517fa27a38b83e5c03de3d0fcad8c6ab8f4ddd0  src/ai4s_engine/decisions.py
0ff8ae8d2a109b7e3f1e72e7a34600adc7d964c5bb5493bc1d5fba914bac3a51  src/ai4s_engine/service.py
6ac70b0265c0b9e39b9220565f4dbc906d57d318c3adfe0a46137dd05d0e8ff8  src/ai4s_engine/sharing.py
b07e200544cf8230329cf3be327748166d195bd27a72a206ff31dfdd72442ab6  src/ai4s_engine/candidate_selection.py
1a3efe793ca3b710cd57256afcf090481f32c4ab4f891cfc96682b42fffa2e91  src/ai4s_query/candidates.py
ef42590ff6e35883689c435ba5cb24a84aaa281e5a32062c17036a344e771113  src/ai4s_query/decision.py
378cd41ba475601e911380a7932e884b6631af148bdfdb1bd572c64325634a39  src/ai4s_workflows/workflows.py
bacaf41fb088ae7037acd5c8bd619228c4d95f2bb161b095e35460362d1866aa  src/ai4s_workflows/cost_decision.py
7872d7cc18032e1097bae9230539de298dade7a64bbefcc347ca4e2c509581a8  tests/test_cost_decision.py
0539a98a2875f9544b158308749fce13ba66cae3b2e6a18ae95bf966fb59d91e  scripts/verify_cost_decision_real.py
```

## 失败尝试与处理

- `real-run.json`：首轮在提交真实阶段前因 daemon 环境缺少 `/usr/bin` 启动失败，只留下 running 开头，不作为验收证据。
- `real-run-2.json`：来源、默认复用、成本复用、成本重算和新采样五个真实阶段已经完成；生成无效 PDB 时使用相对路径，AiiDA `SinglefileData` 拒绝导入，因此最终状态未通过。该文件保留为续跑输入，不改写为成功。
- `real-run-3.json`：从 `real-run-2.json` 的原生 UUID 重新加载前五个阶段，再真实提交失败候选和排除失败候选后的重算任务，最终六项检查通过。

## 已执行检查与限制

- 离线成本决策回归：`PYTHONPATH=src python -m unittest tests.test_cost_decision -v`，32 项通过。
- `python -m py_compile` 已覆盖验证脚本、成本决策相关业务源码和测试文件。
- 本次真实验收证明：在单个真实 Coder／AiiDA Profile、真实 CPU ProteinMPNN、固定输入和受控策略参数下，成本复用、成本判定重算、新采样和失败候选拦截按要求工作。
- `0.733s` 复用耗时仍是按固定开销、产物大小、带宽和物化参数计算的估算值；本次真实证据没有实测实际读取／搬运耗时。默认带宽和物化开销尚未标定。
- 未证明跨机器收益、更大产物收益、成本策略优于 LRU，也未接入 Lotaru 预测模型。一次来源样本不能代表长期或异构环境性能。

返回：[成本决策说明](../../docs/cost_decision.md) · [当前状态](../../docs/status.md) · [仓库](../../README.md)。
