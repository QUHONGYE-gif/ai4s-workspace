# C模块：编排、重算与恢复

当前提供轻量 mock CalcJob → 产物门禁 → 筛选的两阶段 WorkChain，支持最多两次重试和复用上游结果重新筛选。真实 ProteinMPNN 接入、GPU 运行与 daemon 中断恢复需分别验收。

## 环境准备

在个人 Coder 工作区使用已安装的 AiiDA 环境：

```bash
cd /home/coder/ai4s-workspace
source ~/.venvs/aiida/bin/activate
python -m pip install --no-deps -e .
chmod +x src/ai4s_workflows/bin/mock_mpnn.py
verdi daemon restart
```

首次启动可用 `verdi daemon start 1`。插件新增或代码修改后，需要刷新 editable 安装并重启本人 daemon，确保 worker 加载新模块；已有终止任务保留，另行提交新任务验证。

使用指向 `mock_mpnn.py` 的本人 `InstalledCode`，调用 `submit_workchain("mock-mpnn@localhost", threshold=1.08, top_k=2)`。mock 有 40% 的随机失败概率，用于手动观察重试，不能据此评价真实模型的可靠性。

计算、工作流和解析器入口分别为 `ai4s.light-mpnn`、`ai4s.protein-mpnn-filter`、`ai4s.light-mpnn`，入口名不包含分组前缀或冒号。已有 Code 若仍以旧入口调用 `get_builder()`，需将其默认插件改为 `ai4s.light-mpnn`；`submit_workchain` 会直接使用工作流类创建 builder。

## 执行与结果

- `LightMPNNCalcJob` 用 `SandboxFolder.open()` 写入 `params.json` 和 `input.pdb`，取回 `result.json`。
- `LightMPNNParser` 将取回文件解析为 `result: Dict`；缺失结果返回 101，非法 JSON 返回 102。
- WorkChain 仅在 `is_finished_ok` 时读取结果；`Excepted`、`Killed` 和非零退出均进入有限重试。两次重试表示总计最多三次提交。
- 新结果与复用结果都检查 schema、产物列表和支持版本。筛选通过 `calcfunction` 创建输出，保留输入依赖及 creator；输出仍为 `selected_sequences`、`sample_table`、`selection_report`。
- `rerun_filter_only(old_wc_pk, ...)` 复用原任务的上游 `result`，不再次提交 MPNN。builder 中的 code、pdb_file、mpnn_params 用于满足输入声明；筛选阶段不执行它们。

## 最小验证

```bash
source ~/.venvs/aiida/bin/activate
python tests/test_aiida_workflows.py
```

测试会创建独立临时 profile 和 daemon，使用 CPU mock 验证文件输入、Parser、筛选输出来源、一次失败后的重试、重试上限、异常子任务和仅重筛选。测试 wrapper 固定 mock 的成功或失败次序，保留手算预期样本 `s001/s002`；结束后停止测试 daemon，不使用本人现有 profile。普通 pytest 收集会跳过此独立集成测试。
