# C模块：编排、重算与恢复
> 负责：两阶段WorkChain生成‑校验‑筛选；最多2次重试；局部重算复用上游；daemon中断恢复
> 目录：src/ai4s_workflows

## 环境准备
```bash
cd /home/coder/ai4s-workspace
export PYTHONPATH=$PWD/src:$PYTHONPATH
chmod +x src/ai4s_workflows/bin/mock_mpnn.py
verdi daemon start 1

备注：重筛选场景，虽然 builder 仍然传入`code`、`pdb_file`、`mpnn_params`，但由于提供了`existing_mpnn_result`，WorkChain 会直接跳过 MPNN 推理阶段，**上述三个输入不会被执行调用**，仅用于满足 builder 对象的输入声明完整性。