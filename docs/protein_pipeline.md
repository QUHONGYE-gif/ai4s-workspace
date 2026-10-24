# 蛋白质设计程序使用说明

[控制脚本](../scripts/protein_design_pipeline.py) 依次调用 RFdiffusion、ProteinMPNN、本地 MMseqs2 搜索和 Boltz-2，生成一条无条件单链设计。控制层仅使用 Python 标准库；模型、权重、数据库与运行环境需事先准备。当前未接入工作台 API，也没有跨运行结果缓存。

## 环境与配置

真实模型执行使用 Linux、已授权的单张 NVIDIA GPU，以及相互独立的 RFdiffusion／ProteinMPNN 和 Boltz Conda 环境。执行前核查设备、磁盘、现有任务和项目资源约定，见[环境说明](environment.md)。

复制[示例配置](../configs/protein_design.example.json) 到忽略目录后修改路径：

```bash
mkdir -p .local
cp configs/protein_design.example.json .local/protein-design.json
```

`root`、`conda`、`rfd_env`、`boltz_env` 和 `msa.database` 必须填实际绝对路径；示例路径不是已部署环境，JSON 不展开环境变量。`gpu` 为单卡编号；长度、扩散／采样步数、种子及温度都在配置中。源码提交、PyTorch／DGL／Boltz 版本也由配置固定，不兼容时应重新准备环境，不跳过版本检查。

脚本期望数据根目录包含：

```text
<root>/
├── src/RFdiffusion/          # models/Base_ckpt.pt 和对应依赖
├── src/ProteinMPNN/          # vanilla_model_weights/v_48_020.pt
├── tools/mmseqs/bin/mmseqs
└── cache/boltz/              # boltz2_conf.ckpt 及模型所需资料
```

## 运行

以下命令从仓库根目录执行；先将数据目录占位值改为实际位置。先查看计划；`--dry-run` 不调用模型、不检查 GPU／安装环境，也不创建运行目录。

```bash
PROTEIN_DATA=/path/to/protein-data
python scripts/protein_design_pipeline.py run \
  --config .local/protein-design.json \
  --out "$PROTEIN_DATA/runs/design-001" --dry-run
```

`msa.mode=swissprot` 时，先用本地可信的压缩 FASTA 建库；`msa.mmseqs_version` 须与已安装二进制的 `version` 输出一致，数据库前缀必须尚不存在：

```bash
python scripts/protein_design_pipeline.py build-db \
  --config .local/protein-design.json \
  --fasta-gz "$PROTEIN_DATA/db/uniprot_sprot.fasta.gz"
python scripts/protein_design_pipeline.py run \
  --config .local/protein-design.json \
  --out "$PROTEIN_DATA/runs/design-001"
```

原始 FASTA 保持不变，数据库旁的 `.source.json` 记录源文件、二进制和库文件身份。`register-db` 仅用于来源已知的 CPU 库登记，不能证明任意未知库对应所给 FASTA。`msa.mode=empty` 跳过搜索；搜索无有效候选时也明确使用单序列预测。

GPU 搜索需另装 `<root>/tools/mmseqs-gpu/bin/mmseqs`，将 `msa.backend` 改为 `gpu`、填写该工具版本，并选择新的数据库前缀。`build-db` 会生成 padded 库；GPU 搜索使用 `--gpu 1`，不传 CPU 灵敏度 `-s`。安装条件和后端差异以 [MMseqs2 官方说明](https://github.com/soedinglab/MMseqs2/wiki) 为准。当前 GPU 统一封装入口仍需在目标环境端到端验收。

## 输出与检查

每次使用新的 `--out`；已有目录会被拒绝。输出包含 `rfd/`、`mpnn/`、`msa/`、`inputs/`、`boltz/`、`logs/`、配置和脚本快照，以及带命令、状态和文件哈希的 `manifest.json`。成功前检查预测结构、单链序列、样本数量、置信度有限性和 NPZ 压缩包完整性；失败目录保留。`completed` 表示文件及连接检查通过，不表示功能或生物学效果成立。

运行不需要仓库中的实验记录或历史结果。无需 GPU 的手写输入边界检查：

```bash
python -m unittest discover -s tests -p 'test_protein_design_pipeline.py' -v
```

返回：[仓库入口](../README.md) · [PyMOL 结构查看](../tools/pymol_web/README.md)。
