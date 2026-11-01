# Boltz：本版支持说明

依据：Boltz 2.2.1 的 src/boltz/main.py；单蛋白输入形式参照官方 docs/prediction.md。版本与原始来源见模型定义中的 code_identity、source_url。

本版单蛋白预测配置：recycling_steps（整数、官方默认 3）、sampling_steps（整数、官方默认 200）、diffusion_samples（整数、官方默认 1）。本服务为演示设置了上限，不是普适科学推荐范围。

输入可以是规范的氨基酸序列、上传 FASTA 的一条明确记录，或 ProteinMPNN 输出的某条设计记录。sequence_to_boltz_yaml 转换必须由适配层实现并验证，图上连线不表示已经实现转换。

msa_mode 是产品字段，选 empty 时表示显式单序列模式，将 YAML protein.msa 设置为 empty；选 precomputed 时需要 A3M 文件，并检查首条查询序列与当前蛋白一致。它不是 --msa_mode CLI 参数。不自动启动外部 MSA 服务或下载数据库。空 MSA 不等于拥有同源序列，也不能保证预测效果。

输出结构 CIF 和置信度 JSON。配置生成、环境可用、真实预测和功能验证是不同状态；本服务不执行 Boltz。
