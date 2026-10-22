# 蛋白质流程产物复用与加速：协作讨论材料

整理：陈铠洲；更新：2026-10-22。状态：供陈铠洲与曲鸿烨共同讨论的草稿，尚未经过双方确认。依据为 R001–R004 真实产物及固定版本源码；没有进行缓存开/关计时对照，没有测得加速比。文档与代码位于个人开发分支 [`dev-ckz`](https://github.com/QUHONGYE-gif/ai4s-workspace/tree/dev-ckz)，尚未获准合入 `main`。模型调用、参数与全部材料导航见 [流程说明](protein_pipeline.md)，真实运行身份见 [R001](../experiments/R001-protein-design-smoke/record.md)、[R002](../experiments/R002-swissprot-msa/record.md)、[R003](../experiments/R003-pipeline/record.md)、[R004](../experiments/R004-mmseqs-gpu/record.md)。

## 1. 当前结论与证据范围

已验证的是流程能生成并连接产物，以及工具中存在部分缓存/跳过机制。R003 日志显示 `Using cached IGSO3.`；R002 已建的 Swiss-Prot 库在 R003 被再次使用。当前控制脚本始终要求新输出目录，**尚未实现跨运行的科学结果缓存或自动复用策略**。

R004 还实际复用了 R003b 的设计 FASTA，从搜索步骤继续运行，说明上游结果可以作为后续分支输入；这次没有重跑骨架与序列生成，也没有测量自动复用策略的收益。CPU/GPU 使用相同查询和源 FASTA，但阳性命中集合及筛选 A3M 不同，不能仅凭查询相同就将两个后端的搜索结果视为等价缓存。具体结果统一见 [R004 CPU 对照](../experiments/R004-mmseqs-gpu/record.md#结果及-cpu-对照)。

本文中的“已核实”指运行或固定版本源码提供依据；“建议／候选”是 Codex 整理的讨论方案；第 5 节为待双方确认内容，未形成共同决定。

源码行为、实际使用和性能收益需分别判断：发现缓存分支不等于证明命中正确；观察到缓存命中也不等于测出了加速比。以下提出复用条件和评测候选，供团队选择下一步，不能作为已验证研究收益引用。

## 2. 哪些产物可以复用

复用要区分“把旧产物作为新任务输入”和“相同请求直接返回旧结果”。例如同一骨架可生成多条序列，但不同温度的新序列不能直接复用旧序列并声称重新采样。

| 产物 | 可以怎样复用 | 必须核对的条件 / 何时失效 |
| --- | --- | --- |
| 模型权重、Conda 环境 | 多次任务共享部署，省去重复下载安装 | 平台、依赖、源码和权重哈希；环境存在不代表兼容 |
| RFdiffusion IGSO3 数值表 | 同参数下加载已计算的旋转噪声查找数据 | 扩散/调度参数及实现版本；不能把表当作设计结果 |
| 骨架 PDB | 同一骨架上改变 MPNN 温度、种子或约束，多次设计序列 | 坐标、链、残基编号及约束映射；骨架改变后需重新设计 |
| `.trb` | 解释骨架来源、恢复实际配置及残基映射 | 必须匹配同一骨架与源码；不是任意扩散步骤的完整续算 checkpoint |
| 扩散轨迹 | 可视化过程、比较中间几何 | 主要是分析材料；当前没有验证轨迹直接恢复完整模型状态的接口 |
| MPNN FASTA | 同一序列进行不同预测/分析，省去重新设计 | 精确序列与链；返回旧样本不能替代新随机采样 |
| MPNN 概率/评分 NPZ | 位置偏好、序列质量分析 | 依赖骨架、模型、顺序、约束和序列；自回归概率不能按位置独立采样并声称等价于原模型 |
| Swiss-Prot FASTA 和 MMseqs2 库 | 多查询共享一份库，省去下载、解压与 createdb | 固定数据库快照与建库工具版本；改变库会改变搜索含义 |
| GPU padded 目标库 | 同一目标库的多个 GPU 查询共享，省去重复 `makepaddedseqdb` | 记录源 FASTA、普通库、GPU 工具版本和库文件哈希；CPU 普通库与 padded 库分别管理，不能仅按库名前缀互换 |
| MSA 搜索结果、A3M | 相同查询与搜索条件时直接复用；同序列的 Boltz 多次预测共享 A3M | 完整序列/链、库快照、工具、参数、过滤及去重规则；设计序列一改，旧 A3M 不能直接沿用 |
| 无命中结果 | 相同查询和条件下复用“本次无命中”记录 | 是有范围的负面证据；更换数据库、阈值或工具后须重新搜索 |
| Boltz `processed/` | 同输入及兼容版本下省去重复解析与 MSA 预处理 | 需核对序列、MSA 文件哈希、链、模板、约束、配体及预处理参数；同名目录不是身份验证 |
| Boltz 最终结构、置信度 | 对同一预测请求直接展示、比较、可视化 | 模型、输入、采样/循环参数和种子均匹配；新采样请求不能直接返回旧结构 |
| PyMOL 会话及图片 | 演示、检查结构叠合 | 结构来源和残基对应关系；图片不能代替原始 PDB 与数值 |

最低建议：保留输入及哈希、配置、版本/权重哈希、日志、最终 PDB/FASTA/A3M、置信度、`.trb`、来源与状态。轨迹和搜索临时库可按预算讨论保留，但本次不删除已有文件。

## 3. 模型已经有哪些缓存或跳过机制

以下区分源码核实与本次运行验证，不将缓存存在自动解释为跨请求正确复用。

| 工具 | 已核实行为 | 限制 |
| --- | --- | --- |
| RFdiffusion | `rfdiffusion/diffusion.py::_calc_igso3_vals` 将 IGSO3 数值表写为 pickle，已有文件则加载；`model_runners.py` 从 schedule 目录传入缓存路径 | 表文件名包含部分调度参数，未做完整源码/参数内容寻址；共享前仍要核对版本及相关参数 |
| RFdiffusion | `scripts/run_inference.py` 的 `inference.cautious` 在同名 PDB 已存在时跳过；`design_startnum=-1` 可顺延编号 | 检查文件存在，不核对请求身份、配套 `.trb` 完整性或参数一致性 |
| ProteinMPNN | 一次 CLI 调用加载模型后可处理多条样本/骨架；源码提供保存 score/probs、score-only、条件/无条件概率模式 | 本轮调用路径未发现跨独立 CLI 请求的持久结果缓存；NPZ 不等于通用推理状态缓存 |
| MMseqs2 | `createdb` 建好的序列库可被不同查询重复搜索 | 当前未预建大型 `createindex`；没有测量其空间开销和搜索收益，不把“已建库”描述为“已建完整索引” |
| MMseqs2 GPU | R004 用同一 padded 目标库完成设计与天然阳性两种查询；查询库、结果库及 tmp 分开保留 | 是目标库复用的运行证据；不是查询结果缓存，也没有验证 `gpuserver` 常驻服务或自动恢复搜索 |
| Boltz 2.2.1 | `main.py` 的下载逻辑检查 cache 中模型与分子资料是否存在；`--cache` / `BOLTZ_CACHE` 控制位置 | 本地下载缓存主要省网络和部署开销，不代表跳过前向推理 |
| Boltz 2.2.1 | `process_inputs` 根据 processed record ID 跳过已有预处理；`process_input` 遇已有 MSA NPZ 可跳过解析 | 主要依据 ID/路径存在性，未核对新输入内容；改了同名 YAML 或 MSA 后可能误用旧预处理 |
| Boltz 2.2.1 | `filter_inputs_structure` 根据 predictions 下已有的目标目录跳过预测；`--override` 改变预测跳过行为 | 目录存在不证明结构完整；`--override` 不等于清空所有旧预处理。改变输入使用新输出目录最容易避免误复用 |

源码核查入口（固定版本，避免依赖个人审阅目录）：

- RFdiffusion：[`diffusion.py`](https://github.com/RosettaCommons/RFdiffusion/blob/86507b6538f51fce57b5a72477165f03999ed7ae/rfdiffusion/diffusion.py)、[`model_runners.py`](https://github.com/RosettaCommons/RFdiffusion/blob/86507b6538f51fce57b5a72477165f03999ed7ae/rfdiffusion/inference/model_runners.py)、[`run_inference.py`](https://github.com/RosettaCommons/RFdiffusion/blob/86507b6538f51fce57b5a72477165f03999ed7ae/scripts/run_inference.py)。
- ProteinMPNN：[`protein_mpnn_run.py`](https://github.com/dauparas/ProteinMPNN/blob/8907e6671bfbfc92303b5f79c4b5e6ce47cdef57/protein_mpnn_run.py)。
- Boltz 2.2.1：[`main.py`](https://github.com/jwohlwend/boltz/blob/cb04aeccdd480fd4db707f0bbafde538397fa2ac/src/boltz/main.py)，提交对应官方 `v2.2.1` 标签；本轮也核对了已安装 2.2.1 源码中的相应分支。
- MMseqs2：[`createdb` 官方说明](https://github.com/soedinglab/MMseqs2/wiki#creating-a-seqdb-from-a-fasta-file)，本轮实际工具身份见 [R002](../experiments/R002-swissprot-msa/record.md)。Wiki 为持续更新说明，不代替运行时版本记录。

已使用 IGSO3 缓存的运行证据见 [R003 日志](../experiments/R003-pipeline/evidence/rfd.log)，命令身份见 [原始清单](../experiments/R003-pipeline/evidence/manifest.json)。完整归档尚未进入团队共享存储，获取边界见 [流程文档](protein_pipeline.md#7-共享与接手事项)。

## 4. 可以讨论的加速方法

| 方法 | 预期减少的开销 | 证据状态与取舍 |
| --- | --- | --- |
| 保留权重、数值表、序列库 | 重复下载、安装、数值表计算和建库 | 机制已核实；具体加速比未测 |
| 同一骨架批量采样 MPNN | 重复模型加载，部分重复计算 | 官方 CLI 提供样本数与 batch；封装当前只验证一条，扩大后须核对数量和显存 |
| 相同序列共享已验证 A3M | 重复搜索和比对 | 需要建立完整的查询与库身份，不能仅凭文件名 |
| 固定目标库切换 GPU 搜索 | 搜索计算时间 | R004 已跑通，CPU/GPU 结果有差异；这是计算后端变化，需独立对照，不能记为缓存收益 |
| 已验证科学产物直接返回 | 完整的重复科学计算 | 是工作台可研究的策略；当前封装未实现全局结果缓存 |
| 兼容的 Boltz CUDA kernels | 部分推理计算时间 | 本轮为兼容关闭；启用前需匹配 GPU/驱动/依赖并进行同条件检查 |
| 减少 RFdiffusion/Boltz 步数、recycles 或样本数 | 推理时间、部分内存 | 会改变计算条件，可能影响质量；不是无损缓存，需对照评价 |
| 减少 MSA 深度、缩小库 | 搜索、存储、MSA 特征计算 | Swiss-Prot 已用于演示，但可能降低召回；不能从无命中推广到所有数据库 |
| 长驻模型进程、合并查询 | 重复初始化或搜索调度 | 工程候选，当前未实现、未测；不在学习阶段先建设服务框架 |

## 5. 与曲鸿烨需要共同确认的内容

1. 原型先复用哪种产物：Codex 建议从固定数据库、搜索后端和精确序列的 A3M 开始，规则较清楚；骨架作为下游输入复用也容易展示。
2. 采用哪些身份字段与有效性条件；特别是同名不同内容、数据库更新、链映射变化和无命中结果。
3. 如何度量首次生成、重复计算、读取、传输的耗时与空间；需要真实测量才可报告收益。
4. 哪些中间产物用于解释与追溯，哪些值得缓存；运行失败或写入不完整的结果不能作为可复用完成项。

以上是待讨论建议，不是已确认研究控制点。建议首次对照至少记录：输入/环境/参数身份、冷启动与已有缓存两种状态、端到端及分阶段耗时、产物读取/传输时间、缓存大小、结果是否完整且对应当前请求。相同结果直接返回与改变参数后重新计算分别统计；不要将减少步数、缩小数据库造成的变化归因为缓存收益。

接下来的协作交付可在本文更新：双方确认的首个复用对象、失效条件、测量方案和实际结果。尚未确定负责人分工、团队共享存储或评价阈值，不预先写成共同决定。当前不据此实现新的缓存策略、删除策略或工作台业务。

讨论前可共同查看三组现成材料：

- [R003 MSA 摘要](../experiments/R003-pipeline/evidence/msa-summary.json)：理解无命中结果的适用范围及下游 `empty` 分支。
- [R004 CPU/GPU 比较](../experiments/R004-mmseqs-gpu/evidence/cpu-gpu-comparison.json)：讨论为什么搜索后端必须进入身份字段。
- [R004 全文件清单](../experiments/R004-mmseqs-gpu/evidence/inventory-final.json)：按实际字节数讨论数据库、临时文件和最终产物的保留成本；清单本身不提供所有文件下载，获取状态见 [流程文档第 7 节](protein_pipeline.md#7-共享与接手事项)。

双方讨论后的决定继续写在本节，并标明确认日期、适用输入和修改原因；原始实验记录保留历史条件。后续真正开展新实验时再建独立运行记录，不能把本次观察改写成对未来策略的验证。

相关文档：[流程与命令](protein_pipeline.md) · [设计草案](research_plan.md) · [当前状态](status.md) · [仓库入口](../README.md)。
