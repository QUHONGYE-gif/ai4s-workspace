# R004：MMseqs2 GPU 搜索分支

状态：GPU 搜索与两个 Boltz 分支真实运行完成，2026-10-21；完整目录已归档至租用平台持久卷，完整包与小型证据包均已回传校验。CPU 与 GPU 分支分别保留，未覆盖 R001–R003。

## 目的与执行边界

从 [R003b 的设计 FASTA](../R003-pipeline/evidence/design.fasta) 分出 GPU MSA 路径，使用同一份 Swiss-Prot FASTA；另用相同天然人血红蛋白 α 链 P69905 作有命中对照。本轮从已有序列开始，**没有重新运行 RFdiffusion／ProteinMPNN**。上游生成证据来自 R003，下游 GPU 搜索与预测证据来自本记录；这是工作流的分支补齐，不是一次从头重跑所有模型。

成功运行身份为 `R004-mmseqs-gpu/audited-b`。北京时间 22:50:04–22:51:18（UTC 14:50:04.750285–14:51:18.251531），约 73.50 秒，包含两个查询分支。该运行使用独立审计脚本和既有筛选函数，未直接执行新增 GPU 后端的生产 `build-db/run` 入口；不能将本轮描述为该封装入口的端到端验收。

## 执行身份与来源

| 项目 | 已核实信息 |
| --- | --- |
| 平台 | 矩池云恢复实例 `wXO8nR`；与团队 Coder、`lab-gpu` 是不同环境 |
| 资源 | RTX 4090，24564 MiB，驱动 565.77；glibc 2.35；根盘约 300 GB，检查时剩余约 267 GB；持久卷 5 GB |
| 执行根目录 | `/root/ai4s-trial`；R004 目录为其 `runs/R004-mmseqs-gpu/`。仅为历史执行位置，不是团队访问地址 |
| GPU MMseqs2 | 版本 `fcf516aba34be4569b3eb5bda2b9db9e26a8f278`；二进制 SHA-256 `f46fc772abad7417e7ae1bf0f219883fcfc4fa3cdc2ab4117fa6f8bd7e0e9c11` |
| 软件来源 | 官方 `https://mmseqs.com/latest/mmseqs-linux-gpu.tar.gz`，下载包记录 SHA-256 `4e3ce8a250b042ff35d51ce94e79fdfd29c36d6af8ec28c6514f20281eef80a57`；`latest` 会更新，实际二进制以本轮重新计算的哈希锁定 |
| Swiss-Prot | 575,748 条序列；压缩 FASTA 93,801,562 字节、SHA-256 `a9c3496aa727e61d25d9e1291c9ba28d2c2ad19c0e26569dc083d53ec4169536`；解压 FASTA 288,201,213 字节、SHA-256 `1372f18e218d761027616bf17479bcf450b30314fc0a8095fcb0e97e85d6ecf9`。来源解释见 [R002](../R002-swissprot-msa/record.md#执行身份与数据) |
| 设计查询 | 80 aa；FASTA SHA-256 `b8d3aa156dab83dd6a7bd36c35cf18ab560a04046d37c6145ed6fcc6df75caeb`，与 R003b 附件一致 |
| 阳性查询 | P69905，142 aa；源 FASTA SHA-256 `9f28ee2461cfee4c04e56bb447316d0ad23687d15f3da13aaae5946de4f0273a` |
| Boltz 环境 | Python 3.11.13、Boltz 2.2.1、PyTorch 2.6.0+cu124、NumPy 1.26.4、Lightning 2.5.0；[版本输出](evidence/runtime-versions.txt) |

完整输入、库文件、执行脚本与辅助函数身份在 [成功运行清单](evidence/audited-b/manifest.json)。Boltz 继续使用恢复实例的既有环境和缓存；原模型部署、源码修复及权重身份见 [R001](../R001-protein-design-smoke/record.md)、[R003 清单](../R003-pipeline/evidence/manifest.json)。本轮没有重新计算 Boltz 权重哈希，因此不将历史权重哈希写成当晚重新核验的结果。

## 实际流程与参数

先使用 GPU 二进制 `createdb` 从同一解压 FASTA 建独立普通库，再用 `makepaddedseqdb` 建 GPU padded 库。墙钟分别约 1.652 秒、5.345 秒；[建库日志](evidence/logs/createdb-swissprot.log)、[padded 日志](evidence/logs/makepaddedseqdb-swissprot.log) 及同目录 JSON 保存了实际命令、开始结束时间、退出码与日志哈希。建库是准备步骤，不称为 GPU 搜索。

两个分支均依次执行：查询 `createdb` → `search --gpu 1` → `convertalis` → `result2msa --msa-format-mode 5` → `unpackdb` → 筛选去重 → Boltz。关键搜索参数为：

```text
CUDA_VISIBLE_DEVICES=0
search QUERY PADDED_DB RESULT TMP --gpu 1
-e 0.001 --max-seqs 500 --threads 10
-a 1 --alignment-mode 3 --min-seq-id 0.3 -c 0.8 --cov-mode 2
```

`--cov-mode 2` 为查询覆盖度；一致性 ≥0.3、查询覆盖 ≥0.8、E≤0.001。GPU 搜索采用最高灵敏度，不传 CPU 的 `-s 7`。`--max-seqs 500` 是候选上限，不是最终 MSA 深度。日志明确记录 `Use GPU 1`、`ungappedprefilter ... --gpu 1`；导出和筛选步骤不宣称为 GPU 加速。

Boltz 两个分支均使用 `boltz2`、GPU 0、seed 42、recycling 3、sampling 200、diffusion samples 1、PDB 输出、`--no_kernels --num_workers 0`。实际 argv 和每步退出码均在成功清单。执行会话为 `ai4s-R004b`，完成后自动退出；总日志为原运行目录 `logs/audited-b-driver.log`。

## 结果及 CPU 对照

| 观察项 | CPU R003 | GPU R004 |
| --- | --- | --- |
| 设计序列命中 | 0 | 0 |
| 设计 A3M／预测输入 | 只有查询；`msa: empty` | 只有查询；`msa: empty`；Boltz 预测成功 |
| P69905 导出命中 | 498 | 498 |
| P69905 原 A3M | 499 条，含查询 | 499 条，含查询 |
| P69905 筛选去重后 | 464 条，含查询 | 467 条，含查询；466 条非查询序列 |
| P69905 下游验证 | 解析并写出 MSA NPZ；此 A3M 未重跑预测 | 带筛选后 A3M 的完整 Boltz 预测成功 |

CPU/GPU 阳性命中目标共有 487 个，各有 11 个独有目标，名单及 A3M 哈希见 [比较文件](evidence/cpu-gpu-comparison.json)。GPU A3M SHA-256 为 `ae724d3749f39d2dfbfc612330d8c8bb059d894d8818d78f1ead425e467b4d59`。相同候选数不表示相同结果；搜索后端、灵敏度及候选集合均有变化，不能将差异仅归因于 GPU 硬件或把更多记录理解为质量更高。

| 成功分支 | GPU search 墙钟 | Boltz 子命令墙钟 | confidence_score | pTM | complex_plddt |
| --- | ---: | ---: | ---: | ---: | ---: |
| 80 aa 设计 | 0.510 秒 | 36.303 秒 | 0.867168 | 0.749023 | 0.896705 |
| P69905 阳性 | 0.470 秒 | 34.501 秒 | 0.922421 | 0.899979 | 0.928032 |

这些是既有环境与缓存下的单次子命令墙钟，包含调用初始化开销；没有随机重复、冷热缓存控制或 GPU 峰值采样。不得据此计算正式加速比，也未测试峰值显存。没有有／无 MSA 的同对象效果对照，不证明 MSA 提升、功能成立或实验稳定性。

[最终验证](evidence/validation.json) 确认：两条分支各一份预测 PDB、单链序列与查询完全一致、长度分别为 80 和 142、主要置信度字段均有限；设计分支 5 个、阳性分支 6 个 NPZ ZIP 完整。阳性分支实际输入使用筛选后 A3M，并产生 Boltz 的 processed MSA 文件。

本地封装代码复核时修正了新增 staging 检查误拦截 CPU 建库的问题，并将 GPU staging 冲突检查前移至解压之前；9 个确定性测试通过，包含 CPU 建库调用边界及已有 staging 保护。测试没有调用科学模型或本地 MMseqs2，不替代 GPU 封装入口的远程验收。

## 中间产物与记录索引

[完整文件清单](evidence/inventory-final.json) 保存归档前 **206 个条目**，逐文件列出相对运行目录路径、字节数、SHA-256；符号链接另存链接目标。清单不列自身，归档另按整包哈希校验。目录包含：

| 运行内位置 | 内容／解释 |
| --- | --- |
| `db/swissprot_base*`、`db/swissprot_gpu*` | 普通库、padded 库、头库、索引、lookup 与 source 文件 |
| `db/query*`、`db/gpu_hits*`、`tmp/` | 早期交互操作的查询库、搜索结果、prefilter 候选、内部脚本、参数、临时目录和 latest 链接 |
| `audited/` | 首轮审计执行、设计序列 MSA 和预测、失败清单；原样保留 |
| `audited-b/design/`、`audited-b/positive/` | 两条成功分支的 FASTA、查询库、内部命中库、TSV、原始 A3M、筛选 A3M、MSA 摘要、YAML、临时结果和 Boltz 输出 |
| 各分支 `boltz/boltz_results_input/processed/` | 结构、MSA（阳性分支）、记录、分子、约束等预处理产物 |
| 各分支 `boltz/boltz_results_input/predictions/input/` | 预测 PDB、confidence JSON、pLDDT／PAE／PDE NPZ |
| `audited-b/*.log`、`logs/` | 分步日志、总日志、建库时间及退出码 |
| `run_audited*.py`、`finalize.py` | 本轮实际执行与验收脚本快照；依赖记录中的辅助函数和已部署模型环境 |

Git 保存 [48 个小型附件的来源索引](evidence/index.json)，可直接查看 [设计筛选 A3M](evidence/audited-b/design/filtered.a3m)、[阳性筛选 A3M](evidence/audited-b/positive/filtered.a3m)、[设计 PDB](evidence/audited-b/design/boltz/boltz_results_input/predictions/input/input_model_0.pdb) 和 [阳性 PDB](evidence/audited-b/positive/boltz/boltz_results_input/predictions/input/input_model_0.pdb)。大型数据库和完整临时文件保存在完整归档，不纳入 Git。**文件“已在清单记录”与“已附在仓库”分别判断**。

## 失败与修正

1. 首次建库包装依赖不存在的 `/usr/bin/time`，转换未启动。后来 Python 计时建库成功。早期同名建库日志被成功日志覆盖，错误文本此前已见终端并在本记录保留；不能宣称早期失败日志原件完整保留。
2. JupyterLab 曾连接中断；首个交互 GPU 搜索退出 0，但在界面回显延迟时误提交相同命令，重复执行退出 1，覆盖了第一份搜索日志。首次结果和临时目录仍保留；新前缀 `gpu_hits_retry1` 搜索成功、日志保留。不从被覆盖日志推导首轮耗时。
3. `audited/` 中 GPU 搜索及 Boltz 子命令退出 0，但验收代码错误查找 `boltz/predictions/`，缺少实际的 `boltz_results_input/`，断言失败。它是输出定位错误，不是模型推理失败。该目录保持 failed。
4. [修正版脚本](evidence/run_audited_b.py) 使用新目录 `audited-b/`、修正预测定位，重新执行两条分支并验收成功；原目录和失败 manifest 未改写。未启动的终端输入、命令拼接错误不计作模型或科学搜索失败。

## 归档与共享状态

| 归档 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `ai4s-R004-gpu-full-20261021.tar.gz` | 270,256,012 | `c189c457e803d73f64b199d79d61668add4cff189f5b36a12791528e104ee445` |
| `ai4s-R004-gpu-evidence-20261021.tar.gz` | 408,767 | `71b36a5c6ab7a4ba88368d46c81b4d2f85cef688eac97bf86797c8b2696eeaf8` |

完整包包含 R004 的数据库、所有保留下来的临时／中间文件、失败与成功分支；不是整机备份，不含全部模型环境、权重或源 Swiss-Prot FASTA。恢复这些公共依赖需依据 R001–R003 的环境与输入身份重新准备。

两个包均已在实例与持久卷副本间验证哈希一致；持久卷位置为 `/mnt/ai4s-trial-20261021/`，只是原账户备份位置。小型证据包回传后匹配整包哈希，并核验其中 145 个可用普通文件与完整清单一致；它刻意不含全量 DB/tmp。完整包回传后整包 SHA-256 一致，并逐项核验清单中 201 个普通文件的大小／哈希、5 个符号链接目标；另确认归档中的清单自身与仓库副本一致，见 [回传校验结果](archive-verification.json)。陈铠洲保管归档，尚未上传团队共享存储，无团队统一下载链接。服务器没有自动关闭或释放。

相关文档：[CPU R003](../R003-pipeline/record.md) · [流程说明](../../docs/protein_pipeline.md) · [环境说明](../../docs/environment.md) · [状态](../../docs/status.md) · [仓库入口](../../README.md)。
