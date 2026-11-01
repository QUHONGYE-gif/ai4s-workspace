# RFdiffusion：本版支持说明

依据：RosettaCommons/RFdiffusion，提交 86507b6538f51fce57b5a72477165f03999ed7ae；config/inference/base.yaml、scripts/run_inference.py。接口对照日期 2026-10-24。原始来源见模型定义中的 source_url。

本版只配置单链无条件设计。没有目标结构约束时不需要输入 PDB。长度 L 映射为 contigmap.contigs=[L-L]；生成数映射 inference.num_designs；步数映射 diffuser.T。

80 aa、1 个骨架、50 步是本项目样例，不全部是官方默认。固定版本 base.yaml 的 inference.num_designs 是 10。长度 20–512、设计数至多 64 是本演示支持范围，不是模型普适能力或显存保证。

随机性不在本版开放统一 seed 字段；既有科学脚本的 deterministic、design_startnum 语义应由实际适配层处理。输出 backbone（PDB）和 metadata（TRB）。多个骨架需要明确选择，不自动假定全部传入下一步。

本服务只保存配置，不启动 RFdiffusion。
