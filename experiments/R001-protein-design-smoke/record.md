# R001：RFdiffusion → ProteinMPNN → Boltz 最小流程

状态：三步均已完成，退出码均为 0；结果与日志已归档并校验，小型原始证据随本记录提供。日期：2026-10-21（Asia/Shanghai）。

## 目的与边界

在租用的 RTX 4090 上走通一条 80 残基单链的骨架生成、序列设计和结构预测链路，检查每一步的输入、输出及可复用产物。这是流程验证，不是功能设计或实验有效性验证。未指定目标蛋白、结合位点或功能，也未进行湿实验。

## 执行身份

| 项目 | 已核实信息 |
| --- | --- |
| 平台 | 矩池云临时 GPU 实例，NVIDIA GeForce RTX 4090，24564 MiB；驱动 565.77 |
| 工作目录 | `/root/ai4s-trial`（实例盘）；小型结果备份至 `/mnt/ai4s-trial-20261021`（持久卷） |
| RFdiffusion 源码 | `RosettaCommons/RFdiffusion`，提交 `86507b6538f51fce57b5a72477165f03999ed7ae` |
| ProteinMPNN 源码 | `dauparas/ProteinMPNN`，提交 `8907e6671bfbfc92303b5f79c4b5e6ce47cdef57` |
| RFdiffusion 环境 | Conda `rfd4090`，Python 3.10.22、PyTorch 2.0.1+cu118、DGL 1.0.2+cu118、CUDA Toolkit 11.8；运行时需将环境 `lib` 加入 `LD_LIBRARY_PATH` |
| ProteinMPNN 环境 | 复用 `rfd4090`；模型 `v_48_020`、采样温度 0.1、随机种子 42 |
| Boltz 环境 | 镜像 `myconda`，Python 3.11.13、Boltz 2.2.1、PyTorch 2.6.0+cu124；`--no_kernels` |

依赖完整清单在 `logs/rfd-freeze.txt` 与 `logs/boltz-freeze.txt`；两份权重的 SHA-256 在 `logs/model-sha256.txt`。RFdiffusion 环境另外安装了 DGL 1.0.2 的 CUDA 11.8 wheel 与 CUDA 11.8 运行库；Boltz 安装后曾把 PyTorch 升到与该驱动不兼容的版本，已恢复 PyTorch 2.6.0+cu124，并用 `--no_kernels` 完成预测。对应安装与修复日志均保留。这是为 RTX 4090 调整过的环境，不等同于 RFdiffusion 官方旧版 Conda 基线，也未验证 Boltz 可选 CUDA kernel 路径。官方命令和输入约定见 [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion)、[ProteinMPNN](https://github.com/dauparas/ProteinMPNN) 及 [Boltz 预测文档](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md)。

## 步骤与已得到的产物

1. **RFdiffusion**：`contigmap.contigs=[80-80]`，一个设计。第二次运行退出码 0，日志 `logs/rfd-run-02.log`。`results/rfd/mono80_0.pdb` 是骨架；`mono80_0.trb` 保存推理元数据；`results/rfd/traj/` 有两条扩散轨迹 PDB。第一次启动因 DGL 缺 CUDA 11 的动态库失败，日志保留为 `logs/rfd-run.log`；补装 CUDA 11.8 并设置库路径后成功。
2. **ProteinMPNN**：以该骨架 PDB 为输入，产生一条 80 位设计序列。退出码 0，日志 `logs/mpnn-run.log`。`results/mpnn/seqs/mono80_0.fa` 含原骨架序列与设计序列；`results/mpnn/probs/mono80_0.npz` 保存逐位概率；`results/mpnn/scores/mono80_0.npz` 保存评分。传给下游的是 FASTA 最后一条设计序列，非第一条全甘氨酸原骨架序列。
3. **Boltz-2**：输入 `inputs/mono80.yaml`，其中序列自动取自 ProteinMPNN FASTA，`msa: empty` 明确使用单序列模式。退出码 0，日志 `logs/boltz-run.log` 显示 `Number of failed examples: 0`。预测 PDB 为 `results/boltz/boltz_results_mono80/predictions/mono80/mono80_model_0.pdb`；同目录有 `confidence_*.json`、逐残基 pLDDT、PAE 和 PDE 的 NPZ 文件。`processed/` 保存 Boltz 预处理输入。此模式省去 MSA，日志也提示预测可能欠佳；本次运行不含 MSA；后续建库与接入验证见 [R002](../R002-swissprot-msa/record.md)。

## 最小检查与解释

- RFdiffusion PDB 和 Boltz PDB 均有 80 个残基、80 个 Cα 原子；两者按对应 Cα 刚体叠合的 RMSD 为 **0.827 Å**。这只说明在本例中预测结构与设计骨架几何接近。
- Boltz JSON 中 `confidence_score=0.8749`、`ptm=0.8113`、`complex_plddt=0.8908`；这里是模型输出的预测置信度，不是实验验证，也不能证明蛋白会折叠、稳定或具备目标功能。
- ProteinMPNN 采样序列得分为 1.1668；其含义应按模型定义解读，不能跨模型直接与 Boltz 置信度比较。原骨架全为 GLY，下游使用 FASTA 的第二条设计序列。

本次没有指定目标、功能约束、模板或 MSA，也没有独立实验对照。真实任务还需选择目标和设计条件、建立或接入 MSA 搜索，再做有对照的验证。

## PyMOL 可视化

使用独立 Conda 环境 `pymol-vis` 中的开源 PyMOL 3.1.0，执行 [可复现脚本](visualize.pml)；未改动模型运行环境。脚本按残基顺序将两份 PDB 的 80 对 Cα 叠合，PyMOL 报告 RMSD 0.827 Å。

| 图 | 读取方式 |
| --- | --- |
| [骨架与预测结构叠合](figures/overlay.png) | 蓝色半透明为 RFdiffusion 骨架，橙色为 Boltz 预测结构；局部偏差可直接观察。 |
| [Boltz 逐残基 pLDDT](figures/boltz-plddt.png) | 仅显示 Boltz 结构，按 PDB B-factor 着色：红色较低、黄色居中、绿色较高；色标范围 50–100。B-factor 与 `plddt_*.npz` 的 80 位数值已核对。 |

仓库提供原始 [骨架 PDB](evidence/backbone.pdb) 和 [预测 PDB](evidence/prediction.pdb)。安装 PyMOL 后，从仓库根目录执行以下命令，生成图片和可交互会话至 `runs/R001-visualization/`（Git 忽略的运行输出目录）：

```bash
pymol -cq experiments/R001-protein-design-smoke/visualize.pml
```

本次共享版脚本只调整输入/输出位置，叠合和着色命令沿用原始脚本；本轮未重新渲染。已提交图片来自首次成功可视化。

图中的叠合与 pLDDT 是模型之间的几何和置信度检查，不是功能或实验稳定性证明。

## 产物保存

仓库选集：[骨架](evidence/backbone.pdb)、[MPNN FASTA](evidence/sequence.fa)、[预测结构](evidence/prediction.pdb)、[置信度](evidence/confidence.json)；[附件索引](evidence/index.json) 保存源归档内路径与 SHA-256。两幅图位于 `figures/`。选集不是完整归档，轨迹、概率 NPZ、日志等仍在归档中。

完整归档 `ai4s-trial-20261021.tar.gz` 为 475,523 字节，SHA-256 `b5a92e50e55cb888dc9f33d6ecc4914f371e1d6d37e02e029e316c6d32c9f1a5`，已核对 32 个文件并校验回传副本。归档根下为 `inputs/`、`results/`、`logs/`；本记录中的产物路径相对该根目录。陈铠洲保管完整归档，另备份至租用平台持久卷；尚无团队共享下载链接。归档不包含完整模型环境或大型权重；补充源码及环境清单恢复包由 [环境说明](../../docs/environment.md#矩池云临时-gpu-试运行2026-10-21) 维护。

## 原始运行命令

以下保留当时租用实例的执行路径以供审计，不是团队统一部署目录。新运行可参考 [后续封装运行的实际命令](../R003-pipeline/record.md#运行与失败保留)，调整配置并使用新输出目录。

```bash
cd /root/ai4s-trial/src/RFdiffusion
LD_LIBRARY_PATH=/root/miniconda3/envs/rfd4090/lib:${LD_LIBRARY_PATH:-} DGLBACKEND=pytorch \
  conda run --no-capture-output -n rfd4090 python scripts/run_inference.py \
  'contigmap.contigs=[80-80]' \
  inference.output_prefix=/root/ai4s-trial/results/rfd/mono80 \
  inference.num_designs=1 \
  inference.model_directory_path=/root/ai4s-trial/src/RFdiffusion/models

cd /root/ai4s-trial/src/ProteinMPNN
conda run --no-capture-output -n rfd4090 python protein_mpnn_run.py \
  --pdb_path /root/ai4s-trial/results/rfd/mono80_0.pdb \
  --out_folder /root/ai4s-trial/results/mpnn \
  --num_seq_per_target 1 --sampling_temp 0.1 --seed 42 \
  --save_score 1 --save_probs 1

boltz predict /root/ai4s-trial/inputs/mono80.yaml \
  --out_dir /root/ai4s-trial/results/boltz \
  --cache /root/ai4s-trial/cache/boltz \
  --output_format pdb --no_kernels --num_workers 0
```

重跑时应使用新输出目录并保存新的日志；本次 RFdiffusion 与 Boltz 未固定随机种子，不保证重跑得到同一结构。大型权重与完整 Conda 安装未备份；源码及环境清单后来补存于恢复包。环境位置和项目状态分别见 [环境说明](../../docs/environment.md) 与 [当前状态](../../docs/status.md)。
