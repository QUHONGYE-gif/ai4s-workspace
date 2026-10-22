# 蛋白质设计全流程实验报告

整理：陈铠洲　实验日期：2026 年 10 月 21 日　整理日期：2026 年 10 月 22 日

## 实验结论与阅读说明

本次已在一张 RTX 4090 上完成 **RFdiffusion 骨架生成 → ProteinMPNN 序列设计 → Swiss-Prot 本地搜索与 MSA 整理 → Boltz-2 结构预测 → 文件检查与可视化**。CPU 版与 GPU 版 MMseqs2 搜索均已实际运行，并保留输入、输出、中间文件、参数和日志。

实验采用 80 个氨基酸残基的无条件单链设计，目的是掌握常规流程及数据如何在模型之间流转。两次设计序列在本次数据库与各自搜索条件下均没有命中，因此设计蛋白实际完成的是单序列结构预测；另用天然蛋白 P69905 验证了有 MSA 的搜索与完整预测路径。**目前完成的是计算流程验证，尚未验证真实折叠、稳定性、结合能力或生物学功能。**

本文先介绍流程，再按阶段解释原理、实际操作、参数和产物，最后汇总结果、封装命令与交接材料。初学者可顺序阅读正文，准备复现时再查看附录。另一份《蛋白质设计中间产物与复用加速分析》讨论产物怎样重复使用、工具已有机制及后续协作问题。

### 给队友的汇报开场

汇报这项任务时，可以先用一句话概括：**我们把一条蛋白质设计链路跑通了，并检查了每一步产生的文件怎样交给下一步；这次验证的是计算流程，不是已经证明蛋白质具有目标功能。**

接着按下面的主线讲，不必一开始就讲安装命令或所有文件名：

1. 先确定设计对象：本次只规定生成一个 80 aa 的无条件单链，没有指定靶点、结合位点或功能。
2. 用 RFdiffusion 生成主链骨架，得到描述三维坐标的 PDB。
3. 用 ProteinMPNN 根据骨架设计氨基酸序列，得到 FASTA；这里必须选择真正采样出的序列，而不是骨架占位记录。
4. 用 MMseqs2 在 Swiss-Prot 中搜索相似序列，并把结果整理成 MSA。MSA 有命中时提供进化信息；没有命中时明确使用 `msa: empty`，不能借用别的蛋白的 MSA。
5. 用 Boltz-2 根据序列和可选 MSA 预测结构，查看坐标与置信度。
6. 用文件检查和 PyMOL 确认每一步确实接上，并说明哪些结果只是计算证据，哪些问题还没有验证。

每个阶段都建议回答五个问题：**为什么做？输入是什么？使用了什么模型或参数？留下了什么产物？这个结果能说明什么、不能说明什么？** 本文后面的章节按这个顺序展开；队友只想快速了解流程时读到第 1 节即可，准备复现或检查时再读对应阶段。

## 1 从蛋白质设计流程理解这次任务

### 1.1 骨架 序列与预测结构分别是什么

蛋白质由氨基酸依次连接形成。序列是氨基酸的排列顺序，结构是这些残基在三维空间中的位置；骨架主要描述主链的空间形状。80 aa 表示长度为 80 个氨基酸残基。

本次从长度要求出发，先提出一个空间形状，再寻找适合这个形状的序列，最后让结构预测模型根据序列重新预测，检查它是否得到与原骨架接近的形状。这是一次设计与计算检查的闭环。真实研究常常还需要生成许多候选、排序筛选和实验验证，本次只用小样本学习流程。

| 阶段 | 要回答的问题 | 输入与输出 |
| --- | --- | --- |
| RFdiffusion | 可以生成怎样的主链形状 | 长度与设计条件 → 骨架坐标 PDB |
| ProteinMPNN | 哪些氨基酸排列适合这个骨架 | 骨架 PDB → 设计序列 FASTA |
| MMseqs2 与 MSA | 库中有哪些相似序列 怎样对齐 | 设计序列与数据库 → 命中表与 A3M |
| Boltz-2 | 这条序列可能形成怎样的结构 | 序列及可选 MSA → 预测坐标与置信度 |
| 检查与 PyMOL | 文件有没有接对 预测与骨架是否接近 | 序列、骨架、预测 → 一致性检查与叠合 |

用文字串起来就是：

**指定长度 → 生成骨架 → 为骨架设计序列 → 搜索相似序列 → 有合格候选则整理 MSA，无候选则单序列预测 → 查看结构与置信度 → 与原骨架比较。**

MSA 是预测前可加入的信息来源；没有命中时仍可以尝试单序列预测，但不能写成使用了多序列进化信息。Boltz 本次用于结构预测，没有执行功能预测或亲和力预测。

### 1.2 本次实际做了哪些运行

为了先打通连接、再补齐搜索与封装，实验分步推进。下文使用有实际含义的名称区分对象。

| 运行 | 使用的对象与目的 | 实际完成范围 |
| --- | --- | --- |
| 首次手工设计 | 从头生成第一套 80 aa 骨架与序列 | 三模型连接、单序列预测、PyMOL 叠合 |
| 初次 CPU 搜索 | 第一条设计序列和天然 P69905 | 建库、搜索、A3M；天然对照完成带 MSA 预测 |
| CPU 封装设计 | 从头生成第二套 80 aa 骨架与序列 | 固定种子、严格搜索筛选、单命令完整运行 |
| 严格 CPU 阳性补查 | P69905 使用封装中的搜索条件 | 搜索、筛选、Boltz MSA 解析；未做新的完整预测 |
| GPU 搜索补充 | 复用第二条设计序列和 P69905 | GPU 建库与搜索、导出筛选、两条完整预测 |

**两次设计是不同的骨架和序列。** 首次手工结果用于展示结构叠合；封装运行重新设计一个对象，用于验证自动连接；GPU 分支接着第二条序列搜索，没有再次运行骨架与序列设计。不同对象的置信度、RMSD 和耗时分别记录，不能拼成同一个实验结果。

**天然蛋白对照为什么需要单独加入。** 新设计序列可能缺少可检出的天然近邻。为确认“搜索有命中 → 生成多序列 A3M → Boltz 读取并预测”这条路径能工作，本次从同一 Swiss-Prot 快照中提取了已有天然蛋白——人血红蛋白 α 链 P69905，长 142 aa。它绕过前两个设计模型，直接从序列搜索开始。这是搜索与预测链路的阳性对照，不是设计蛋白的功能对照；不能把它的 MSA 借给设计序列使用。

## 2 环境准备与模型部署

### 2.1 实际使用的算力

科学计算在独立租用的矩池云 Linux x86_64 实例上完成，使用单张 RTX 4090，报告显存 24,564 MiB，驱动 565.77。原实例完成手工及 CPU 封装流程，恢复实例完成 GPU 搜索补充；恢复环境 glibc 2.35。实例盘约 300 GB，另有 5 GB 平台持久卷用于归档。

这说明本次短单链案例能在一张约 24 GB 显存的 4090 上跑通。实验没有采样显存峰值，不能据此给出所有长度、复合物或多样本任务的最低显存要求。团队 Coder 是另一套开发环境，本次成功不表示其中已经部署并验证了模型。

### 2.2 为什么用了两套虚拟环境

虚拟环境用于隔离 Python 和依赖；模型源码、模型权重、数据库与运行结果是另外的文件。安装了环境不等于模型就绪，还需要权重、GPU 驱动、兼容的运行库和实际推理检查。

RFdiffusion 依赖较旧的 PyTorch/DGL 组合，Boltz 使用较新的组合，因此分成两套 Conda 环境，由控制脚本分别调用。Conda 在这里管理依赖，不负责产生蛋白质结构。

| 用途 | 环境与主要版本 |
| --- | --- |
| RFdiffusion 与 ProteinMPNN | rfd4090；Python 3.10.22，PyTorch 2.0.1+cu118，DGL 1.0.2+cu118，CUDA Toolkit 11.8 |
| Boltz | myconda；Python 3.11.13，Boltz 2.2.1，PyTorch 2.6.0+cu124；GPU 补充环境另记录 NumPy 1.26.4、Lightning 2.5.0 |
| 可视化 | 独立 pymol-vis 环境；开源 PyMOL 3.1.0 |
| CPU 搜索 | MMseqs2 官方 Linux AVX2 构建 |
| GPU 搜索 | MMseqs2 官方 Linux GPU 构建；与 CPU 工具分开放置 |

RFdiffusion 使用 Base_ckpt.pt，ProteinMPNN 使用 v_48_020，Boltz 使用 boltz2 结构预测模型及 boltz2_conf.ckpt。源码提交、工具身份和权重校验值见附录。

### 2.3 部署中实际解决的问题

RFdiffusion 第一次因 DGL 找不到 CUDA 11 动态库而失败。补装 CUDA 11.8 运行库后，将该环境的 lib 加入 LD_LIBRARY_PATH，设置 DGLBACKEND=pytorch，再次执行成功。

安装 Boltz 时，依赖安装曾将 PyTorch 升级到与实例驱动不兼容的版本；恢复为 2.6.0+cu124，关闭可选 CUDA kernels，并设置 --num_workers 0 后成功。后续沿用这条兼容路径，没有测试可选 kernels 的收益。

本报告记录的是为本次机器调整并实跑过的环境组合。恢复时应同时核对版本和修复记录，不能只装最新依赖，也不能将其称为 RFdiffusion 官方旧版环境的原样复现。

## 3 骨架生成 RFdiffusion

### 3.1 这一阶段在做什么

RFdiffusion 通过学习到的结构分布逐步去噪，生成蛋白主链的空间坐标。本次无条件设计只规定长度，没有输入靶标、motif、结合位点、配体或功能要求。因此模型输出一个候选形状，而不是一个已具有指定功能的蛋白。

| 参数 | 本次设置 | 含义 |
| --- | --- | --- |
| contigmap.contigs | [80-80] | 单链长度固定为 80 |
| inference.num_designs | 1 | 每次只生成一个骨架 |
| 权重 | Base_ckpt.pt | 无条件生成采用的基础模型 |
| diffuser.T | 封装显式设为 50 | 扩散步数；改变步数会改变计算条件 |
| 随机性 | 手工未显式固定；封装固定 42 | 封装设 deterministic，起始编号 42，官方脚本用编号设种子 |
| inference.write_trajectory | 封装设为 True；手工也保存轨迹 | 留下生成过程中的坐标 |

首次成功生成 mono80_0.pdb；封装重新生成 design_42.pdb。编号只是命名的一部分；判断是否同一骨架应比较内容与配置。

### 3.2 得到了哪些产物

**骨架 PDB** 保存残基和原子的三维坐标，是下游 ProteinMPNN 的输入。骨架中的全 GLY（甘氨酸）是占位表示，不能据此认为已设计出全甘氨酸蛋白。

**同名 .trb** 保存推理配置、映射等元数据，解释骨架怎样生成及残基如何对应。它应与同一 PDB 一起保存；本次没有验证用它恢复任意扩散步骤的完整模型状态。其格式使用 pickle，仅应读取可信来源。

**两类轨迹 PDB** 展示逐步生成过程。封装输出为 design_42_Xt-1_traj.pdb 与 design_42_pX0_traj.pdb：前者记录迭代状态，后者记录各步对最终去噪结构的估计。它们适合观察形状怎样形成，不能当作多条独立最终设计。

**日志与配置** 记录模型加载、实际参数、耗时和异常。封装日志出现 Using cached IGSO3.，说明加载了已有旋转扩散数值表；这与复用一个已生成的骨架是两件事。

本阶段检查骨架可读、单链长度为 80，并保留 .trb 与轨迹。首次手工骨架另核对到 80 个 Cα 原子，供后续逐残基叠合。

## 4 序列设计 ProteinMPNN

### 4.1 从空间形状到氨基酸排列

ProteinMPNN 读取骨架几何，为各位置选择氨基酸。它要解决的是“给定形状，哪些序列与它相容”。产生序列之后，仍需要结构预测或实验检查它能否形成目标形状。

| 参数 | 本次设置 | 含义 |
| --- | --- | --- |
| model_name | v_48_020 | 选择序列设计权重 |
| num_seq_per_target | 1 | 每个骨架采样一条设计序列 |
| sampling_temp | 0.1 | 控制采样分布；增大通常增加多样性，质量需另测 |
| seed | 42 | 固定本次采样随机性 |
| batch_size | 封装显式设为 1 | 每批样本数 |
| backbone_noise | 封装显式设为 0 | 不额外扰动输入骨架 |
| save_score 与 save_probs | 均为 1 | 另存评分和概率 |

实际过程为：读取对应骨架 → 采样序列 → 保存 FASTA、评分和概率 → 选择采样记录 → 单独写出下游查询 FASTA。

### 4.2 FASTA 中必须选对哪一条

本次每个 MPNN FASTA 有两条记录：第一条描述原骨架的占位序列，第二条带 sample=1，才是实际设计序列。把第一条 GLY 占位序列送去搜索或预测，会接错流程。封装检查第二条记录的标识、80 aa 长度和氨基酸字符。

首次手工采样得分为 1.1668。这是 MPNN 对序列的模型评分，不是实验成功率，也不能与 Boltz 置信度直接比较。

首次手工设计使用的序列为：

```text
KKEKILEEIEKLIKEGIEAGKSLEELEKKIKELLKKFGFPEETIEEIVEKFKEFYEESKDKEEFIEKAKKYFKEVIEELE
```

第二次即 CPU 封装设计的序列为：

```text
SLLKLLLEEKLKEEKLIEEAKKRIKELLETTKDKEELIEKLEEIAEELEKEPVLEELKELVEERIEDLKAGKEKEYEIKL
```

GPU 搜索使用的正是这条序列，与首次手工设计不是同一个对象。

### 4.3 本阶段产物的用途

| 产物 | 记录的内容 | 下游用途 |
| --- | --- | --- |
| seqs/*.fa | 原骨架记录、设计序列、设置与评分 | 提取设计序列 |
| probs/*.npz | 概率、log 概率及相关数组 | 分析各位置的氨基酸偏好 |
| scores/*.npz | 采样/评分数组 | 分析同条件候选 |
| inputs/design.fasta | 实际选中的一条序列 | 作为搜索查询，并写入 Boltz 输入 |

NPZ 是保存多个数值数组的压缩容器。概率和评分值得留存，但不代表完整推理状态；不能脱离骨架和模型条件，按各位置概率独立抽样后声称等价于原设计过程。

## 5 数据库搜索与 MSA

### 5.1 MSA 数据库和 MMseqs2 的关系

**MSA（Multiple Sequence Alignment，多序列比对）**把多条相关序列按对应位置排齐，使模型能够利用保守位点和序列变化的信息。它通常包含查询本身及多条搜索候选，不是找到一条“最可靠序列”就结束。

这里有三个不同对象：Swiss-Prot 是天然蛋白序列数据库；MMseqs2 是搜索和比对的软件；A3M 是把比对交给 Boltz 的文件格式。A3M 用大写字母和缺口表示对齐位置，小写字母表示相对查询的插入；统计对齐列时不把小写插入计入。

候选通过一致性、覆盖和 E 值筛选，表明满足本次计算规则；是否存在可信生物学同源关系仍需进一步判断。只有查询自身的一条 A3M 没有增加多序列信息。

### 5.2 为什么选择 Swiss-Prot 它有多大

本次为学习本地建库与搜索，选择规模较小、经过人工审校的 UniProtKB/Swiss-Prot，没有部署大型综合库。2026 年 10 月 21 日 16:48 下载快照如下。

| 项目 | 本次实测 |
| --- | ---: |
| 数据库序列数 | 575,748 条 |
| 压缩 FASTA | 93,801,562 字节，约 89.4 MiB |
| 解压 FASTA | 288,201,213 字节，约 275 MiB |
| GPU 补充中生成的普通库文件组 | 317,583,909 字节 |
| GPU padded 库文件组 | 319,799,125 字节 |

数据库下载在运行模型的服务器。源 FASTA、普通库和 padded 库是不同表示，不能只用压缩大小估计全部磁盘需求。环境、权重、临时文件与预测还需额外空间。下载源 current_release 会更新，复现以保存文件的哈希为准。

### 5.3 两条搜索路径如何连接

CPU 路径先用 createdb 将 FASTA 转成 MMseqs2 目标库，查询也用 createdb 转成查询库。随后执行：

**search → convertalis 导出命中 TSV → result2msa 生成比对库 → unpackdb 导出 A3M → 阈值筛选与去重 → 检查首行与列数 → 写入 Boltz 输入。**

GPU 路径从同一 FASTA 另建普通库，再用 makepaddedseqdb 转成适合 GPU 搜索的布局；用独立 GPU 二进制执行 search --gpu 1。下游仍需导出和筛选，不把这些步骤统称为 GPU 加速。两种查询共用 padded 目标库，查询、结果和临时目录分别保存。

本次未预建大型 createindex，也未使用 gpuserver 常驻服务。createdb、padded 转换与搜索的作用和计时分别记录。

### 5.4 搜索和筛选参数怎样解释

初次 CPU 搜索使用 -s 7 -e 0.001 --max-seqs 500 --threads 10。这一轮没有显式设置 0.3 一致性、0.8 查询覆盖阈值，也未显式精确计算一致性，TSV 的 fident 为估计值。

CPU 封装及严格阳性补查增加以下设置，GPU 保留同样阈值，但灵敏度机制不同。

| 参数 | 严格 CPU 与 GPU 设置 | 含义 |
| --- | --- | --- |
| -s | CPU 为 7；GPU 不传 | CPU 搜索灵敏度；GPU 采用最高灵敏度 |
| --gpu | CPU 不启用；GPU 为 1 | 开启 GPU 搜索 |
| -e | 0.001 | 随机出现此类匹配的期望数量阈值，不是同源概率 |
| --min-seq-id | 0.3 | 本次定义下一致性至少 30%，非通用同源判据 |
| -c 与 --cov-mode | 0.8 与 2 | 覆盖至少 80% 查询，限制仅短片段相似的候选 |
| -a 与 --alignment-mode | 1 与 3 | 保留回溯并显式计算一致性 |
| --max-seqs | 500 | 搜索阶段候选数量控制，非最终 MSA 深度 |
| --threads | 10 | CPU 线程数 |
| --msa-format-mode | 5 | 导出 A3M |

导出后再次按 TSV 的一致性、查询覆盖与 E 值筛选。去重时，去掉小写插入、点号和缺口后比较对齐主序列，保留查询一条，剔除与查询相同或此前已保留的重复主序列。A3M 首行必须与查询一致，各行对齐列数必须匹配长度。

“命中数”“A3M 记录数”“有效序列深度 Neff”不同。这里报告的深度是文件记录数，含查询；本次未计算反映序列多样性的 Neff。

### 5.5 设计序列与天然对照的实际结果

| 查询与条件 | 搜索命中 | 原始 A3M 含查询 | 最终交付 MSA 记录 | 下游完成情况 |
| --- | ---: | ---: | ---: | --- |
| 首次设计，初次 CPU | 0 | 1 | 1，仅查询 | 原设计仍为单序列预测 |
| P69905，初次 CPU | 500 | 501 | 501，未经后来严格筛选 | 完整带 MSA 预测成功 |
| 封装设计，严格 CPU | 0 | 1 | 1，仅查询 | empty 完整预测成功 |
| P69905，严格 CPU | 498 | 499 | 464，筛选后 | 解析与 MSA NPZ 成功，未完整预测 |
| 同一封装设计，GPU | 0 | 1 | 1，仅查询 | empty 完整预测成功 |
| P69905，GPU | 498 | 499 | 467，筛选后 | 完整带 MSA 预测成功 |

上表所有 A3M 数量均含查询。天然对齐宽度为 142 列，设计为 80 列。初次天然 501 条 A3M 约 75 KiB；500 是设置上限，并不表示库里只有 500 条相关序列。严格 CPU 最终含 463 条非查询，GPU 含 466 条。

**设计为何没有命中。** 已确认的是本次库和参数下未检出命中。人工设计可能没有接近的天然序列，Swiss-Prot 范围也较小；更远关系可能受检索和阈值影响。这些是可能解释，本次没有独立确定原因。不能断言设计失败、结构不存在，或在所有数据库都没有同源。

无命中时仍保存空命中 TSV、仅查询 A3M 和原因摘要，显式使用 msa: empty。这是一条正常的已记录分支，不能伪造候选，也不能借用天然蛋白的 MSA。

### 5.6 CPU 和 GPU 搜索并没有得到相同结果

严格 CPU 与 GPU 天然查询都得到 498 个目标，但仅 487 个共有，另各有 11 个独有。最终 A3M 为 464 对 467 条，内容哈希也不同。

同一查询和源库快照下，构建、搜索实现与灵敏度条件仍有差异。不能仅凭命中数相同视为结果相同，不能把差异只归因于 GPU 硬件，也不能用多出三条记录证明质量更好。目标列表和 A3M 哈希见附录。

### 5.7 本阶段保留的中间文件

| 文件组 | 内容与用途 |
| --- | --- |
| 源 FASTA 与数据库来源记录 | 固定搜索范围、快照和工具身份 |
| 普通目标库与 padded 目标库 | 多查询共享；每个前缀是一组配套文件 |
| query* 与 query_h* | 查询序列库、头库与配套类型/索引 |
| hits* 与 hits.tsv | 内部结果与可读命中明细 |
| alignment* 与 a3m/0.a3m | 内部比对与原始 A3M |
| filtered.a3m 与摘要 JSON | 实际筛选结果、数量、是否交给 Boltz |
| tmp 下的哈希目录与 latest 链接 | blastp.sh、pref_0 预筛选数据与类型/索引 |
| 日志与脚本快照 | 各步命令、耗时、退出码、失败重试 |

TSV 八列为 query,target,fident,alnlen,qcov,tcov,evalue,bits，依次表示查询、目标、一致性、比对长度、查询覆盖、目标覆盖、E 值和比对得分。0 字节设计 TSV 在运行成功且确认无命中时是有效结果，不等于文件损坏。

## 6 结构预测 Boltz

### 6.1 预测输入怎样从上一步得到

Boltz 本次使用结构预测模式，输入包括序列、链标识 A，以及与该序列对应的 A3M 或明确的 empty。没有额外输入配体、模板或功能约束。

下面是格式示例，尖括号内容需替换，不是可直接执行的真实输入。封装写出的 JSON 也是合法 YAML。

```yaml
version: 1
sequences:
  - protein:
      id: A
      sequence: <当前对象的完整序列>
      msa: empty
```

有 MSA 时将 msa 改成该对象实际 A3M 的路径。本次使用本地搜索，没有调用在线 MSA 服务；预测前核对 YAML 序列、搜索查询与 A3M 首行一致。

| 参数 | 封装与 GPU 补充设置 | 含义 |
| --- | --- | --- |
| --model | boltz2 | 结构模型 |
| --seed | 42 | 固定随机性；首次手工未显式固定 |
| --recycling_steps | 3 | 循环精炼次数 |
| --sampling_steps | 200 | 结构生成的去噪步数 |
| --diffusion_samples | 1 | 一个结构样本 |
| --accelerator 与 --devices | gpu 与 1 | 单张可见 GPU |
| --no_kernels | 开启此开关 | 关闭可选 kernels，沿用兼容路径 |
| --num_workers | 0 | 数据加载设置 |
| 输出格式 | 封装和 GPU 为 PDB | 初次天然完整预测为 CIF，两者均保存坐标 |

上表种子、循环和采样数是后续封装/GPU 显式设置，不能追溯说首次手工也固定了全部相同参数。

### 6.2 Boltz 还生成了什么

Boltz 先解析输入并写出 processed，再预测并写出 predictions。实际指定的输出目录下还有 boltz_results_加输入文件名这一层，验收不能忽略它。

| 产物 | 怎么理解 |
| --- | --- |
| PDB 或 CIF | 预测坐标，用于查看、叠合与分析 |
| confidence JSON | 整体置信度、pTM、平均 pLDDT 等 |
| plddt NPZ | 局部置信度数组，可逐残基着色 |
| pae NPZ | 估计的成对对齐误差，反映区域相对位置的不确定性 |
| pde NPZ | 估计的成对距离误差 |
| processed 中 structures 与 mols | 解析后的结构/分子数据 |
| processed 中 records 与 constraints | 输入记录与约束数据 |
| processed MSA NPZ | 有 MSA 时解析出的比对数据；天然 GPU 分支确实生成 |
| manifest 与 hparams.yaml | 处理记录和推理配置，与外层控制清单分别保存 |

首次手工和封装设计均完成完整预测；初次天然 CPU A3M、天然 GPU A3M 也都完成预测。严格 CPU 的 464 条 A3M 仅验证解析与 MSA NPZ 写入，必须与完整预测区分。

### 6.3 怎样读置信度

pLDDT 表示模型对局部结构的置信度，pTM 反映对整体拓扑的置信度，confidence_score 是 Boltz 综合置信指标。它们不是蛋白真实存在或具备功能的概率。

本次 complex_plddt 的 JSON 数值约为 0–1，逐位 NPZ/PDB 着色采用 0–100 尺度，读图需核对。不同对象或不同输入的指标可以并列报告，不能据此证明 MSA 增益。

| 对象与实际输入 | confidence_score | pTM | complex_plddt |
| --- | ---: | ---: | ---: |
| 首次手工设计，empty | 0.8749 | 0.8113 | 0.8908 |
| P69905，初次 CPU 的 501 条 A3M | 0.930688 | 0.913338 | 0.935025 |
| CPU 封装设计，empty | 0.867168 | 0.749023 | 0.896705 |
| 同一封装设计，GPU 搜索后仍 empty | 0.867168 | 0.749023 | 0.896705 |
| P69905，GPU 的 467 条 A3M | 0.922421 | 0.899979 | 0.928032 |

严格 CPU 的 464 条 A3M 没有新完整预测指标。初次天然 CPU 与后来 GPU 的 MSA、搜索条件等不同，没有同一对象有/无 MSA 对照，因此不下“MSA 提高预测效果”的结论。

## 7 文件检查与 PyMOL 可视化

### 7.1 怎样确认流程接对了

按连接顺序检查：骨架残基数与链 → 选中 MPNN 采样记录 → 搜索 FASTA 与 Boltz 序列一致 → A3M 首行与对齐列数正确 → 预测序列与输入一致 → 结构数量、置信度和 NPZ 完整性。

CPU 封装设计的 80 aa 预测序列与输入完全一致，成功清单中的 67 普通文件回传后逐项核对大小与 SHA-256，全部匹配。GPU 两成功分支各有一个 PDB，长度分别为 80 和 142，序列与各自查询完全一致，主要置信度有限；设计 5 个、天然 6 个 NPZ 的 ZIP 完整性通过，天然实际生成 processed MSA。

命令退出 0 只是第一层检查。一些工具会跳过失败样本，目录也可能只写一部分；必须检查具体文件。文件完整、序列接对与科学有效分别判断。

### 7.2 首次设计的结构叠合

PyMOL 3.1.0 按残基顺序将首次骨架与对应预测的 80 对 Cα 刚体叠合，RMSD 为 **0.827 Å**。它衡量叠合后对应原子的偏差，本例说明两模型的形状接近；不是与真实实验结构的比较。

![首次手工设计的骨架与预测叠合](assets/protein_pipeline/backbone-overlay.png)

图 1 蓝色半透明为骨架，橙色为对应预测。沿用首次成功可视化原图，本次整理没有重跑模型或结构渲染。

**0.827 Å 只属于首次手工设计。** 后来封装生成了新骨架和序列，未计算这个 RMSD，GPU 分支也不能沿用。

### 7.3 预测局部置信度着色

![首次手工设计的预测置信度着色](assets/protein_pipeline/prediction-plddt.png)

图 2 仅显示首次设计的 Boltz 结构，采用本次自定义 50–100 色标：红色较低、黄色居中、绿色较高。PDB B-factor 与 NPZ 中 80 位 pLDDT 已核对；此处该字段承载预测置信度，不按晶体实验热运动参数解释。局部置信度高不等于已证明功能。

## 8 流程封装 实际耗时与失败修正

### 8.1 封装替我们完成了什么

控制脚本 protein_design_pipeline.py 调用已部署的官方模型和 MMseqs2，把文件交接、参数和检查串起来。它提供 build-db、register-db 与 run，没有重写模型，也不是一键安装器。

CPU 后端已完成从新骨架开始的端到端实跑。脚本保存配置和自身快照，预检 GPU、环境、源码与权重，依次设计、搜索、预测，检查结构、序列、数量、置信度和 NPZ 后才标记完成。失败则保存异常与日志。

后续增加 GPU 参数和 padded 建库支持，9 项本地确定性测试通过；**新增统一 GPU build-db/run 入口尚未远程端到端验收。** GPU 成功使用的是独立审计脚本。搜索流程跑通与统一入口验收是两项不同结论。

每次 run 必须使用新输出目录，不覆盖、不自动中断续算，也没有自动跨运行匹配科学结果的缓存。

### 8.2 单次运行耗时

CPU 封装于北京时间 18:09:36–18:11:29 完成，端到端约 **112.45 秒**，包含预检、Conda/模型初始化和转换，不含安装、下载与首次建库。“CPU”只指 MMseqs2，RFdiffusion 和 Boltz 仍用 GPU。

| 子步骤 | CPU 封装设计 | GPU 补充设计 | GPU 补充天然查询 |
| --- | ---: | ---: | ---: |
| RFdiffusion | 38.255 秒 | 未重跑 | 不适用 |
| ProteinMPNN | 3.472 秒 | 未重跑 | 不适用 |
| MMseqs2 search | 11.035 秒 | 0.510 秒 | 0.470 秒 |
| Boltz | 46.721 秒 | 36.303 秒 | 34.501 秒 |

GPU 成功运行在 22:50:04–22:51:18，两查询及下游合计 **73.50 秒**；createdb 1.652 秒、padded 转换 5.345 秒另计。它与一条从头设计的 112.45 秒工作量不同，不能直接计算加速比。子步骤不含所有外层开销，相加也不等于总时长。

没有重复计时、冷热缓存控制、I/O/传输测量或显存峰值监测。以上是单次墙钟，用于认识成本分布，不是正式性能基准。

### 8.3 失败过什么 怎样修正

除部署问题外，CPU 封装预检曾因源码目录有未跟踪 outputs/ 停止。核实为 Hydra 自动生成配置/日志目录、无受管源码修改后，仅允许该生成目录，同时保留 Git 状态和 patch，其余源码变化仍检查。成功使用新目录，原失败现场保留。

严格 CPU 天然补查的辅助命令曾把阈值写成 .3/.8，MMseqs2 报参数错误；改为 0.3/0.8 后在新目录成功。主封装本来使用完整小数，不受此辅助错误影响。

GPU 首次建库包装依赖不存在的 /usr/bin/time，转换未启动；改为 Python 计时成功。Jupyter 回显延迟还导致搜索重复提交：首次退出 0 后重复命令失败并覆盖首份日志；首次结果/tmp 保留，之后新前缀重试成功。建库也有早期同名失败日志被覆盖的情况，不能声称全部早期日志原件完整。

第一轮 GPU 审计中，搜索和模型退出 0，但验收漏找 boltz_results_input/ 层级而失败。保留原失败目录，修正后换新目录重跑，才得到通过检查的两条结果。这说明模型成功与整条流程验收通过需要分别判断。

## 9 完成范围与团队交接

模型环境已部署并有真实推理；简化数据库、CPU/GPU 搜索、MSA 连接、参数及产物记录均已完成；CPU 全流程已封装并实跑，命令见附录。两次设计得到序列和结构预测，天然对照补齐有 MSA 的完整路径。复用与加速机制已整理为第二份报告，仍需与曲鸿烨讨论确认方案。

未完成：指定靶标/功能设计、多聚体与配体、多候选筛选、湿实验、MSA 效果对照、正式性能对照、统一 GPU 入口端到端验收，以及工作台自动产物管理与复用。这些不能写成已完成成果。

原始材料由陈铠洲保管，主要归档已回传核验并在平台持久卷备份，**尚无团队统一下载链接**。附录档名用于准确交接，不表示大家已经能自助下载。脚本和配置保存在个人开发分支 dev-ckz；文件名为 scripts/protein_design_pipeline.py 与 configs/protein_design.matpool.json。这是取得代码后的相对位置，不是数据下载入口；原配置含历史实例路径，换机器必须调整。

两份关机补充包仅在平台持久卷保存并校验，尚未回传；正常下载被组织策略屏蔽，已停止尝试。须保留原账户同区域网盘，通过获准通道交接。恢复包不含整个 Conda、全部权重与 Boltz cache，需重新安装下载核验，并再次验证环境，不能当成可解压运行的整机镜像。归档复核未代用户关闭实例，也不能据此判断实例当前是否运行。

## 附录 A 参数与复现命令

### A1 已验证 CPU 封装的使用方式

以下是取得代码并部署完成后，在 Linux GPU 环境中使用的模板。相对文件名以代码包根目录为基准，变量对应接手者实际获分配的数据目录和 Conda 位置，不是个人机器路径。先修改配置的 root、conda、rfd_env、boltz_env、gpu 和 msa.database，JSON 不自动展开环境变量。

```bash
# 将三个值替换为实际位置
export AI4S_CONFIG="/实际数据目录/pipeline-config.json"
export AI4S_FASTA_GZ="/实际数据目录/db/uniprot_sprot.fasta.gz"
export AI4S_NEW_RUN="/实际数据目录/runs/一次新的运行"

# 新建普通目标库
python scripts/protein_design_pipeline.py build-db \
  --config "$AI4S_CONFIG" --fasta-gz "$AI4S_FASTA_GZ"

# 仅看计划 不验证模型安装或 GPU
python scripts/protein_design_pipeline.py run \
  --config "$AI4S_CONFIG" --out "$AI4S_NEW_RUN" --dry-run

# 资源检查通过后运行完整流程
python scripts/protein_design_pipeline.py run \
  --config "$AI4S_CONFIG" --out "$AI4S_NEW_RUN"
```

已有来源明确的 CPU 库时，用 register-db --config ... --fasta-gz ... 替代 build-db；本次实际复用了既有库。登记不能证明任意未知库与 FASTA 对应。输出目录必须新建，失败后也保留现场。长任务使用具名 tmux 并保存日志，启动前检查分配的 GPU、内存、磁盘与已有任务。

### A2 GPU 实验的搜索命令结构

下列变量需绑定实际文件；这组命令仅展示建库、搜索与导出，还需筛选、Boltz 与验收，不能单独当作完整流程。GPU 使用独立二进制。

```bash
"$MMSEQS_GPU" createdb "$SWISSPROT_FASTA" "$BASE_DB"
"$MMSEQS_GPU" makepaddedseqdb "$BASE_DB" "$PADDED_DB"
"$MMSEQS_GPU" createdb "$QUERY_FASTA" "$QUERY_DB"
CUDA_VISIBLE_DEVICES=0 "$MMSEQS_GPU" search \
  "$QUERY_DB" "$PADDED_DB" "$HITS_DB" "$TMP_DIR" \
  --gpu 1 -e 0.001 --max-seqs 500 --threads 10 \
  -a 1 --alignment-mode 3 --min-seq-id 0.3 -c 0.8 --cov-mode 2
"$MMSEQS_GPU" convertalis "$QUERY_DB" "$PADDED_DB" "$HITS_DB" "$HITS_TSV" \
  --format-output query,target,fident,alnlen,qcov,tcov,evalue,bits
"$MMSEQS_GPU" result2msa "$QUERY_DB" "$PADDED_DB" "$HITS_DB" "$ALIGNMENT_DB" \
  --msa-format-mode 5
"$MMSEQS_GPU" unpackdb "$ALIGNMENT_DB" "$A3M_DIR" \
  --unpack-name-mode 1 --unpack-suffix .a3m
```

GPU 官方预编译包要求 Linux glibc ≥2.29、NVIDIA 驱动 ≥525.60.13，无需另装 CUDA Toolkit；恢复环境满足要求。这与 RFdiffusion 所需运行库不同。统一脚本 GPU 路径还需 msa.backend=gpu、独立库前缀和工具身份，由 build-db 生成 padded 库；该统一入口仍待真实端到端验收，不能称为已验收用法。

### A3 完整预测命令结构

在正确 Boltz 环境使用当前对象输入和新输出目录：

```bash
boltz predict "$INPUT_YAML" --out_dir "$NEW_BOLTZ_OUT" \
  --cache "$BOLTZ_CACHE" --model boltz2 --accelerator gpu --devices 1 \
  --output_format pdb --no_kernels --num_workers 0 --seed 42 \
  --recycling_steps 3 --sampling_steps 200 --diffusion_samples 1
```

同名 YAML/MSA 改变后继续用旧目录可能误用旧预处理。本次封装要求新输出目录；固定种子也不保证跨硬件、版本逐位相同。

## 附录 B 产物交接明细

### B1 CPU 封装成功目录

以下为归档内相对位置，供取得材料后识别，不是下载入口。

```text
config.json / pipeline.py / manifest.json / checks.json
logs/                         环境与各命令日志
rfd/design_42.pdb / .trb       骨架与元数据
rfd/backbone.pdb               骨架副本
rfd/traj/                     两类轨迹
mpnn/seqs/ / probs/ / scores/  序列 概率 评分
inputs/design.fasta / design.yaml
msa/database.source.json      库来源
msa/query* / hits* / alignment* / tmp/
msa/hits.tsv / a3m/0.a3m / design.filtered.a3m / summary.json
boltz/boltz_results_design/processed/
boltz/boltz_results_design/predictions/design/
boltz/boltz_results_design/lightning_logs/
```

预测目录有 design_model_0.pdb、confidence_design_model_0.json、plddt/pae/pde 对应 NPZ。processed 包括 structures NPZ、mols PKL、records JSON、constraints NPZ。设计为 empty，不要求出现多序列 MSA 特征。日志保留源码 Git 状态/patch、环境清单、版本和实际命令；manifest 保存状态、时间、命令/工作目录、退出码、耗时与哈希。

首次手工的对应位置为 results/rfd/、results/mpnn/、inputs/mono80.yaml、results/boltz/boltz_results_mono80/ 和 logs/。初次 CPU 搜索包含双查询 inputs/msa_queries.fasta、results/msa_hits.tsv、设计 results/msa/0.a3m、天然 1.a3m、inputs/hba_with_msa.yaml、results/boltz-msa-control/，以及源压缩 FASTA 和 CPU 工具。

### B2 GPU 完整中间文件范围

最终清单 **206 条：201 普通文件、5 符号链接，不含清单自身**。普通文件共 638,444,528 字节，完整压缩包 270,256,012 字节；大小/哈希、链接目标和清单副本均核验。它覆盖保留下来的现场，不表示全部早期日志原件无缺失。

| 目录类别 | 条目数 | 内容 |
| --- | ---: | --- |
| audited-b/ | 91 | 两成功分支、命令、日志、预测、验收 |
| audited/ | 46 | 首次验收失败分支与状态 |
| db/ | 33 | 普通/padded 库、交互查询、结果与重试 |
| logs/ | 13 | 建库、转换、搜索重试与驱动日志 |
| tmp/ | 10 | 早期预筛选数据、脚本、链接 |
| msa/ | 3 | 早期交互导出 |
| __pycache__/ | 3 | 实际字节码，保留现场 |
| 根文件 | 7 | 执行/验收、配置、版本、比较和验证 |

成功 design/ 与 positive/ 各有 query.fasta、query*、query_h*、hits*、hits.tsv、alignment*、a3m/0.a3m、filtered.a3m、msa-summary.json、tmp/、input.yaml、checks.json、Boltz 输出。库前缀配套序列数据、.dbtype/.index/.lookup/.source 及 _h 头库和类型/索引。tmp 有 blastp.sh、pref_0 及类型/索引，latest 链接指向运行哈希目录。

两分支 Boltz 实际位置为 boltz/boltz_results_input/；processed 含 manifest、structures、mols、records、constraints，天然另有 MSA NPZ；predictions 含 PDB、confidence、pLDDT、PAE、PDE；lightning_logs 有 hparams。根文件包括真实脚本快照、cpu-source-config.json、runtime-versions.txt、cpu-gpu-comparison.json、validation.json，用于核对执行、来源和检查结果。

### B3 归档名称与保存状态

以下主要归档已回传核验，由陈铠洲保管，另有平台持久卷备份；尚无统一下载链接。部分档名保留历史编号，只用于准确识别文件。

| 归档名 | 字节数 | 内容 |
| --- | ---: | --- |
| ai4s-trial-20261021.tar.gz | 475,523 | 首次手工设计，32 文件核验 |
| ai4s-msa-20261021.tar.gz | 113,163,185 | 初次搜索、天然预测、源 FASTA、CPU 工具；26 普通文件 |
| ai4s-pipeline-20261021.tar.gz | 503,724 | CPU 封装成功与失败材料；成功 67 普通文件核验 |
| ai4s-msa-positive-check-20261021.tar.gz | 85,449 | 严格 CPU 阳性搜索与解析，无新预测 |
| ai4s-R004-gpu-full-20261021.tar.gz | 270,256,012 | GPU 全部保留现场、DB/tmp、失败/成功和清单 |
| ai4s-R004-gpu-evidence-20261021.tar.gz | 408,767 | 小型证据包，145 普通文件，无全量 DB/tmp |
| ai4s-recovery-20261021.tar.gz | 38,067,041 | 358 条目；源码/SE3、schedules、修复、脚本输入、Conda 导出 |
| audit.tar.gz | 54,303 | 缓存机制核查所用安装源码 |

尚未回传、仅在平台持久卷校验保存的两包：

- ai4s-shutdown-extra-20261022.tar.gz：247,486,566 字节，62 文件/链接条目另附清单；CPU DB/tmp、日志配置、精确 GPU 发布包和收尾日志。
- ai4s-source-generated-20261022.tar.gz：636,205 字节，53 文件另附清单；Hydra 配置/日志、MPNN 官方示例输出。

GPU 完整包不含源 Swiss-Prot FASTA，源文件在初次 MSA 包；初次 MSA 包不含全部解压库，CPU DB/tmp 在未回传补包，也可按固定源文件与版本重建。CPU 封装原包保留 tmp/latest 链接，提取副本未创建该链接。小型证据选集、清单与完整归档不是同一种交付范围。

## 附录 C 版本与校验信息

哈希用来确认字节身份，不证明生物学有效；汇报时不必逐条讲述。

```text
RFdiffusion 源码提交
86507b6538f51fce57b5a72477165f03999ed7ae
ProteinMPNN 源码提交
8907e6671bfbfc92303b5f79c4b5e6ce47cdef57
CPU/GPU MMseqs2 版本字符串相同 构建不同
fcf516aba34be4569b3eb5bda2b9db9e26a8f278
GPU MMseqs2 二进制 SHA-256
f46fc772abad7417e7ae1bf0f219883fcfc4fa3cdc2ab4117fa6f8bd7e0e9c11
GPU MMseqs2 原始发布包 SHA-256
4e3ce8a250b42ff35d51ce94e79fdfd29c36d6af8ec28c6514f20281eef80a57
Swiss-Prot 压缩 FASTA SHA-256
a9c3496aa727e61d25d9e1291c9ba28d2c2ad19c0e26569dc083d53ec4169536
Swiss-Prot 解压 FASTA SHA-256
1372f18e218d761027616bf17479bcf450b30314fc0a8095fcb0e97e85d6ecf9
RFdiffusion Base_ckpt.pt SHA-256
0fcf7d7c32b4848030aca3a051e6768de194616f96ba6c38186351a33bfc6eca
ProteinMPNN v_48_020.pt SHA-256
c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd
Boltz boltz2_conf.ckpt SHA-256
090e82ac8c92f5e943fa1b39e7410a44027bea7243c0bbb3caa67a77fc1428e1
CPU 封装实际脚本 SHA-256
f59cbe99eb26ba64716a7089d3b6081c9b9fcef050cb8c57f38047edb3e58cc7
```

权重哈希在 CPU 封装时核实；恢复 GPU 补充当晚未重新算 Boltz 权重哈希。扩展后的当前脚本也不同于上述 CPU 历史脚本，复现须匹配相应快照。

```text
第二条设计查询 FASTA SHA-256
b8d3aa156dab83dd6a7bd36c35cf18ab560a04046d37c6145ed6fcc6df75caeb
P69905 查询 FASTA SHA-256
9f28ee2461cfee4c04e56bb447316d0ad23687d15f3da13aaae5946de4f0273a
严格 CPU 筛选 A3M SHA-256
cea3f0e6059f98662c25ce1a06adc5c2512e912ffe0fba056c009ed02ac2807d
GPU 筛选 A3M SHA-256
ae724d3749f39d2dfbfc612330d8c8bb059d894d8818d78f1ead425e467b4d59
CPU 独有目标
P02053 P02081 P24292 P68065 P68194 P68232
P68234 P68256 P68257 P68258 Q28221
GPU 独有目标
P02020 P02042 P02050 P02089 P02093 P02102
P06642 P67823 P67824 P86391 Q7M2Y5
```

### C1 归档 SHA-256

```text
ai4s-trial-20261021.tar.gz
b5a92e50e55cb888dc9f33d6ecc4914f371e1d6d37e02e029e316c6d32c9f1a5
ai4s-msa-20261021.tar.gz
c41b990099597931819957d2a85a0508af5b003802cbfbb1f5f3e4049f370116
ai4s-pipeline-20261021.tar.gz
97f3a7178a02d36e6c0c3b1472118b9a4c7a26841f6d2edb8031e8837e3a951b
ai4s-msa-positive-check-20261021.tar.gz
eeab281ede8d595a9af502a1ecc8a7097339643792eb3fe0a8503b6b0b37ed72
ai4s-R004-gpu-full-20261021.tar.gz
c189c457e803d73f64b199d79d61668add4cff189f5b36a12791528e104ee445
ai4s-R004-gpu-evidence-20261021.tar.gz
71b36a5c6ab7a4ba88368d46c81b4d2f85cef688eac97bf86797c8b2696eeaf8
ai4s-recovery-20261021.tar.gz
5123f78c6d243037f0679002cd5e828156f572d5d7d3c9842660c5e522f378e9
audit.tar.gz
0765e3c81e8cad51a764122b1763418829852cde2b12a4347d66352cca6fa18a
ai4s-shutdown-extra-20261022.tar.gz
54b39bce052fed250e2d246497c4e2d1ad7072688c692da33ec0794ba4fc0faf
ai4s-source-generated-20261022.tar.gz
704fed74d93891807881928fcd305722b0f166d51340b21e2461f99f23d19b4c
```

## 附录 D 官方资料

以下资料供进一步学习，本文实验叙述不依赖这些链接才能读懂。

- RFdiffusion：[官方仓库](https://github.com/RosettaCommons/RFdiffusion)。
- ProteinMPNN：[官方仓库](https://github.com/dauparas/ProteinMPNN)。
- Boltz：[官方仓库](https://github.com/jwohlwend/boltz)与[固定版本预测说明](https://github.com/jwohlwend/boltz/blob/v2.2.1/docs/prediction.md)。
- MMseqs2：[官方说明](https://github.com/soedinglab/MMseqs2/wiki)，包括 GPU 搜索、建库与导出。
- Swiss-Prot：[UniProt 官方 FASTA](https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz)，地址会更新，本次快照以哈希确定。
