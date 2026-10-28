# R002：Swiss-Prot 小型 MSA 搜索链路

状态：序列库下载、MMseqs2 搜索、A3M 生成及天然蛋白的 Boltz-2 对照预测均已完成；归档及回传副本已核验。日期：2026-10-21。

## 问题与边界

验证能否用相对小的公开天然蛋白序列库，为 Boltz-2 准备可追溯的 MSA。分别搜索 [R001](../R001-protein-design-smoke/record.md) 的 80 残基 ProteinMPNN 设计序列和人血红蛋白 α 链 P69905。后者是搜索流程的阳性对照，不是 R001 设计的功能对照。本轮没有证明设计序列具备天然同源物、功能或实验稳定性。

## 执行身份与数据

| 项目 | 已核实信息 |
| --- | --- |
| 环境 | 矩池云临时 RTX 4090 实例；本轮 MMseqs2 搜索使用 CPU，Boltz-2 预测使用 GPU；模型环境沿用 R001 |
| 序列源 | [UniProtKB/Swiss-Prot 官方 FASTA](https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz)，2026-10-21 16:48 下载；压缩文件 93,801,562 字节（约 89.4 MiB），解压 288,201,213 字节（约 275 MiB）；MMseqs2 搜索日志显示目标库有 575,748 条序列 |
| 搜索工具 | [MMseqs2 官方 AVX2 二进制](https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz)，`mmseqs version` 输出 `fcf516aba34be4569b3eb5bda2b9db9e26a8f278` |
| 本轮临时目录 | `/root/ai4s-trial/`；序列库在 `db/`，查询在 `inputs/`，结果在 `results/`，日志在 `logs/` |


Swiss-Prot 压缩源 SHA-256：`a9c3496aa727e61d25d9e1291c9ba28d2c2ad19c0e26569dc083d53ec4169536`。

发布包的 `latest` 与数据库的 `current_release` URL 可随时间更新；复现实验时应核对实际版本和数据库快照。备份仅包含压缩序列 FASTA，MMseqs2 数据库可由其重建；大型模型环境和权重不在本轮备份中。

## 实际步骤与结果

1. 用 `mmseqs createdb` 将解压后的 Swiss-Prot FASTA 建为本地搜索库。搜索日志报告目标库有 575,748 条序列。
2. 从 R001 的 ProteinMPNN FASTA 第二条记录提取设计序列；从 Swiss-Prot 提取 P69905 全长序列，合成两条查询。搜索命令使用 `-s 7.0 -e 0.001 --max-seqs 500 --threads 10`，结果经 `convertalis` 导出为 `results/msa_hits.tsv`。字段依次为 `query,target,fident,alnlen,qcov,tcov,evalue,bits`。
3. `designed_mono80` 在该库和这些参数下 **0 条命中**。此结果不能推广为“没有天然同源序列”；不能把只含查询自身的 `results/msa/0.a3m` 当成真实多序列 MSA。R001 的 `msa: empty` 仍是如实描述。
4. `HBA_HUMAN_P69905` 达到每查询 500 条命中的设置上限，前列命中多为全长覆盖且 E 值极低。`result2msa --msa-format-mode 5` 与 `unpackdb` 生成 `results/msa/1.a3m`（约 75 KiB）；这是阳性对照的 MSA。
5. 将 `1.a3m` 置于 Boltz 输入 `inputs/hba_with_msa.yaml` 的 `msa` 字段，运行 `boltz predict ... --no_kernels --num_workers 0`。日志显示 `Number of failed examples: 0`，输出包括 `predictions/hba_with_msa/hba_with_msa_model_0.cif`、置信度 JSON、pLDDT／PAE／PDE NPZ，以及预处理目录。证明本次 A3M 可被 Boltz 接受；置信度不是实验验证。

## 关键命令

以下为当时租用实例的历史执行命令；路径只用于说明运行身份。新环境可参考 [后续封装运行的实际命令](../R003-pipeline/record.md#运行与失败保留)，并调整配置。

```bash
cd /root/ai4s-trial
tools/mmseqs/bin/mmseqs createdb db/uniprot_sprot.fasta db/swissprot
tools/mmseqs/bin/mmseqs createdb inputs/msa_queries.fasta db/queries
tools/mmseqs/bin/mmseqs search db/queries db/swissprot db/hits tmp/search \
  -s 7.0 -e 0.001 --max-seqs 500 --threads 10
tools/mmseqs/bin/mmseqs convertalis db/queries db/swissprot db/hits results/msa_hits.tsv \
  --format-output query,target,fident,alnlen,qcov,tcov,evalue,bits
tools/mmseqs/bin/mmseqs result2msa db/queries db/swissprot db/hits db/msa_result \
  --msa-format-mode 5
tools/mmseqs/bin/mmseqs unpackdb db/msa_result results/msa \
  --unpack-name-mode 1 --unpack-suffix .a3m
boltz predict inputs/hba_with_msa.yaml --out_dir results/boltz-msa-control \
  --cache cache/boltz --no_kernels --num_workers 0
```

## 归档与共享状态

完整归档 `ai4s-msa-20261021.tar.gz` 为 113,163,185 字节，SHA-256 `c41b990099597931819957d2a85a0508af5b003802cbfbb1f5f3e4049f370116`，26 个普通文件；已核对原实例、持久卷及回传副本。归档根下为 `inputs/`、`results/`、`logs/`、`db/`、`tools/`；本记录的产物路径相对该根目录。陈铠洲保管完整归档，另有租用平台持久卷备份，尚无团队共享下载链接。归档保留压缩 FASTA 和 MMseqs2 发布包，未保存可重建的完整搜索库及大型模型环境。

仓库可直接查看：[查询 FASTA](evidence/queries.fasta)、[设计序列单行 A3M](evidence/designed.a3m)、[天然阳性对照 A3M](evidence/positive.a3m)、[命中表](evidence/hits.tsv)、[Boltz 对照日志](evidence/boltz-positive.log)、[置信度 JSON](evidence/confidence.json)。[附件索引](evidence/index.json) 给出各文件在原归档中的路径及哈希，选集不是完整运行归档。

回传核对：设计 A3M 1 条记录、天然对照 A3M 501 条记录，对齐列数分别为 80、142；命中表为天然对照的 500 行，Boltz 日志失败数为 0。本轮未启用显式一致性计算，TSV 的 `fident` 是估计值，不能当作精确序列一致性；这也是后续 R003 调整搜索参数时需要区分的条件。

## 下一步检查

回传及文件结构检查已完成。封装及更严格的 A3M 筛选见 [R003](../R003-pipeline/record.md)。若要为 R001 设计序列取得更深的 MSA，可比较更大或更适合该目标的序列库、搜索灵敏度与匹配质量；任何新命中须检查覆盖率、低复杂度影响和生物学合理性，不能只因有命中就视为可靠同源。

相关文档：[R001 运行记录](../R001-protein-design-smoke/record.md) · [环境说明](../../docs/environment.md) · [当前状态](../../docs/status.md) · [仓库入口](../../README.md)。
