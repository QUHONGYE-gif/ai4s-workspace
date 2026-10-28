# ProteinMPNN：本版支持说明

依据：dauparas/ProteinMPNN，提交 8907e6671bfbfc92303b5f79c4b5e6ce47cdef57，protein_mpnn_run.py。接口对照日期 2026-10-24。source_url 定位完整入口。

该版本 argparse：num_seq_per_target 是整数，官方默认 1；sampling_temp 是温度字符串，官方默认 "0.1"，允许多个温度，但本演示只支持一个；seed 官方默认 0，0 表示随机选择种子，42 是本项目示例值；pdb_path_chains 默认空字符串。

本服务使用 num_seq_per_target、sampling_temp、seed 三个配置字段。温度越高通常增大序列多样性，不保证结构或功能更好。8 条、温度 0.1、种子 42 为演示调用，不把 8 和 42 说成官方默认。

输入 backbone 是真实 PDB 或明确的上游 PDB 输出引用。用户确认设计全部链，或选择实际文件中的部分链；不能凭空宣称一定有 A/B 链。输出设计 FASTA 与分数文件。ProteinMPNN 输出 FASTA 的第一条可能是骨架／原序列记录，传给 Boltz 应明确选择真实设计记录（例如 sample=1）。

用于导入演示的调用片段（示例值）：
python protein_mpnn_run.py --pdb_path inputs/backbone.pdb --num_seq_per_target 8 --sampling_temp 0.1 --seed 42 --out_folder outputs/mpnn

命令中的路径只作为资料，不转换成可访问服务器文件。文件需用户上传或绑定已支持的上游输出。本服务不执行该命令。
