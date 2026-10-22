# R003：蛋白质设计命令封装验证

状态：封装真实 GPU 验证完成，2026-10-21；归档回传并逐项校验完成。首轮预检失败与修正后运行分别保存，未覆盖 R001/R002 或失败目录。

## 问题与实现范围

将 [R001](../R001-protein-design-smoke/record.md) 的手工三步模型调用及 [R002](../R002-swissprot-msa/record.md) 的简化 MSA 搜索连成一条命令，保存重要参数、中间产物、运行状态与日志。只验证一个 80 残基无条件单链设计，不涉及功能设计、配体亲和力或所有蛋白设计分支。

入口：[脚本](../../scripts/protein_design_pipeline.py)、[实际配置](../../configs/protein_design.matpool.json)；使用与参数解释见 [流程说明](../../docs/protein_pipeline.md)，协作草稿见 [复用与加速说明](../../docs/protein_reuse.md)。模型源码、环境和数据快照沿用 R001/R002，路径见 [环境说明](../../docs/environment.md)。

## 执行身份与变化

- 单独租用的矩池云实例 `wzM56V`、单张 RTX 4090；执行目录 `/root/ai4s-trial`。
- RFdiffusion deterministic=True，design_startnum=42，因此官方脚本使用设计编号 42 作为随机种子；扩散步数 50。ProteinMPNN seed=42、temperature=0.1、v_48_020、一条序列。Boltz-2 seed=42、recycling=3、sampling=200、一个结构、关闭可选 kernels。
- R001 没有固定 RFdiffusion/Boltz 种子，本轮生成新骨架，不要求与 R001 相同。
- MSA 新增 `-a 1 --alignment-mode 3 --min-seq-id 0.3 -c 0.8 --cov-mode 2`，并对 A3M 候选筛选、去重。是明确改变过的搜索配置，不冒充 R002 原条件。
- 注册 R002 已建 Swiss-Prot 数据库，保存源压缩 FASTA、工具与库文件的哈希；未重新下载或构建大索引。
- 安装源码版本检查、重要包版本检查、权重 SHA-256、执行环境、实际 argv/cwd、命令日志和每个输出文件哈希均在运行目录。执行的脚本 SHA-256：`f59cbe99eb26ba64716a7089d3b6081c9b9fcef050cb8c57f38047edb3e58cc7`，与本次提交的控制脚本逐字节相同。

## 运行与失败保留

首轮 `/root/ai4s-trial/runs/R003-pipeline` 在预检阶段停止：RFdiffusion Git 状态有 `?? outputs/`，这是先前 Hydra 自动生成目录，没有受版本管理的源码改动。封装修正为仅允许这一个生成目录，同时保存原 Git 状态与 patch 日志，其他源码变动仍阻止执行。未删除该目录或覆盖首轮记录。

第二轮实际命令：

```bash
cd /root/ai4s-trial
python protein_design_pipeline.py register-db \
  --config protein_design.matpool.json --fasta-gz db/uniprot_sprot.fasta.gz
tmux new-session -d -s ai4s-R003b \
  'cd /root/ai4s-trial && python protein_design_pipeline.py run --config protein_design.matpool.json --out /root/ai4s-trial/runs/R003b-pipeline > /root/ai4s-trial/logs/R003b-pipeline.log 2>&1'
```

成功运行 UTC 10:09:36.993742–10:11:29.444997（北京时间 18:09:36–18:11:29），总计约 112.45 秒。主模型命令包含 Conda 和模型初始化开销，不能与纯 GPU 推理时间混同。

| 阶段 | 子命令墙钟秒数 | 结果 |
| --- | --- | --- |
| RFdiffusion | 38.255 | 80 残基骨架、`.trb`、两类扩散轨迹；日志显示 `Using cached IGSO3.` |
| ProteinMPNN | 3.472 | 一条 80 位设计序列、概率与评分 |
| MMseqs2 search | 11.035 | 本轮数据库及参数下 0 命中；不推广为所有库无同源 |
| Boltz-2 | 46.721 | 一个预测 PDB，置信度和逐位/成对 NPZ |

设计序列：

```text
SLLKLLLEEKLKEEKLIEEAKKRIKELLETTKDKEELIEKLEEIAEELEKEPVLEELKELVEERIEDLKAGKEKEYEIKL
```

MSA 文件只包含查询，`msa/summary.json` 明确 `used_by_boltz=false`；Boltz 输入使用 `msa: empty`。不能将本轮称为“设计序列获得了真实同源 MSA”。

## 必要验证与结论

运行中的检查确认骨架 80 残基、预测结构单链序列与 ProteinMPNN 设计完全一致、一个预测结构、置信度均为有限值、输出 NPZ ZIP 完整；只有这些检查通过才标记 completed。回传后核对清单中 **67 个文件**的大小及 SHA-256，全部匹配。

Boltz 置信度 `confidence_score=0.8671682477`、`ptm=0.7490227222`、`complex_plddt=0.8967046738`。本轮未做骨架–预测 RMSD，不引用 R001 的 RMSD 作为本轮结果；置信度不证明功能、折叠或实验稳定性。

5 个确定性边界检查通过：选用 MPNN 采样记录、A3M 小写插入不计对齐列、命中必须同时通过筛选并去重、已有运行目录不能覆盖、无预测结构不能标记完成。测试入口：`python -m unittest discover -s tests -p 'test_protein_design_pipeline.py' -v`。这些检查不代替真实模型执行。

## MSA 有命中分支的补充检查

为覆盖新筛选逻辑的有命中分支，用 R002 同一 P69905 阳性对照，在 CPU 上运行相同搜索参数、筛选与去重，并调用已安装 Boltz 2.2.1 的 `parse_a3m`，未重复 GPU 结构预测。搜索 498 条候选，原 A3M 499 条记录；过滤查询重复项及重复比对主序列后，保留 463 条非查询序列，最终 A3M 464 条记录、每行 142 对齐列；Boltz 解析并写出 MSA NPZ 成功。

首个辅助检查使用 `.3` / `.8` 小数写法，MMseqs2 报 `Error in argument --min-seq-id`，没有完成搜索；该检查目录 `runs/R003-positive-msa` 保留。改为 `0.3` / `0.8` 后，在新目录 `runs/R003-positive-msa-b` 完成。主封装使用配置数值转换得到 `0.3`，不受该辅助命令格式错误影响。

补充检查归档 `ai4s-msa-positive-check-20261021.tar.gz` 为 85,449 字节，SHA-256 `eeab281ede8d595a9af502a1ecc8a7097339643792eb3fe0a8503b6b0b37ed72`；已保存并校验回传副本。最终过滤后 A3M SHA-256 `cea3f0e6059f98662c25ce1a06adc5c2512e912ffe0fba056c009ed02ac2807d`。仓库提供 [检查结果](evidence/positive-checks.json) 和 [过滤后 A3M](evidence/positive.filtered.a3m)。这验证新筛选产物能被解析；完整“天然蛋白 MSA → 预测”的证据仍来自 R002，未声称有 MSA 提升效果。

## 产物与备份

成功运行身份为 `R003b-pipeline`；原始归档根目录包含 `runs/R003b-pipeline/` 和 `logs/`。首次失败 `R003-pipeline` 及辅助检查失败 `R003-positive-msa` 的目录和日志均保留，未用后续成功覆盖。会话 `ai4s-R003b` 在命令完成后自动结束。

完整运行归档 `ai4s-pipeline-20261021.tar.gz` 为 503,724 字节，SHA-256 `97f3a7178a02d36e6c0c3b1472118b9a4c7a26841f6d2edb8031e8837e3a951b`；回传后逐项核对成功清单中 67 个普通文件的大小及哈希，全部匹配。提取副本不创建 `tmp/latest` 符号链接，原归档仍保留链接。完整归档由陈铠洲保管，另有租用平台持久卷备份，尚无团队统一下载链接。

仓库提供 [原始运行清单](evidence/manifest.json)、[输出检查](evidence/checks.json)、[设计 FASTA](evidence/design.fasta)、[MSA 摘要](evidence/msa-summary.json)、[RFdiffusion 日志](evidence/rfd.log) 及上节阳性补查文件；[附件索引](evidence/index.json) 记录归档内来源、大小及哈希。清单中的绝对路径属于历史执行环境，不是协作访问地址；Git 仅保存附件选集，未包含清单列出的所有产物。

安装源码审阅归档 `audit.tar.gz` 的 SHA-256 为 `0765e3c81e8cad51a764122b1763418829852cde2b12a4347d66352cca6fa18a`，用于核查缓存机制，未作为自有模型代码提交。可公开核查的固定版本源码入口见 [复用讨论稿](../../docs/protein_reuse.md#4-工具自身已有的缓存与跳过机制)。

相关文档：[流程说明](../../docs/protein_pipeline.md) · [复用草稿](../../docs/protein_reuse.md) · [环境说明](../../docs/environment.md) · [当前状态](../../docs/status.md) · [仓库入口](../../README.md)。
