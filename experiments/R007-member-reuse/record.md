# R007：最新成员实现整合与真实跨成员复用

状态：已完成。模块整合、统一内核和两个真实成员容器间的 API／原生节点联调通过。本轮不合并 `main`，不评价蛋白质功能或模型质量。

## 范围与运行身份

- 日期：2026-11-14，Asia/Taipei。工作台基线 `dev-qhy@5aa6185`，在已有干净副本上开发，原本地工作区的未提交修改保留。
- 本记录的执行源码固定于 `50ab0954f1a72da3942ee620efc9733d021143b0`；后续 PR 精简仅整理文档、测试和重复验收入口。证据 JSON 中的源码清单保留运行当时的路径与摘要，不随目录整理改写。
- 纳入成员固定提交及职责见[引擎说明](../../docs/engine_service.md#契约与代码来源)。整合 ckz、csr、wyh 最新 GitHub 实现；不检查或引入 zjx 本轮实现。
- 统一内核：`QUHONGYE-gif/aiida-core@1998e2939123dcb17e845d8fe6716acf5ecba896`，标签 `ai4s-2.9.4-2`，Python 标识 `2.9.4+ai4s.2`。保留团队原有标签、共用环境和个人 profile。
- 执行位置：`lab-gpu` 的 `ai4s-personal-csr-dev` 和 `ai4s-personal-qhy-dev` 两个真实成员容器，分别使用 `ai4s-integration-csr`、`ai4s-integration-qhy`，各自的 SQLite、Repository 和 daemon 独立。没有把两个人的数据库挂在同一容器里模拟。
- 容器代码 `/home/coder/ai4s-integration-20261114`，专用环境 `~/.venvs/aiida-integration-20261114`，配置、工作目录及输出根 `/home/coder/runs/integration-20261114`。结果在宿主机分别落到 `/data1/qhy/runs/{csr,qhy}/integration-20261114/`。
- 宿主机调度与日志 `/data1/qhy/projects/ai4s-integration-20261114/`。服务位于项目内部网络 3013，配置显式成员与 peer token；凭据没有进入本记录或 Git。
- 执行前确认 GPU 上有其他进程，本轮只使用真实 CPU ProteinMPNN，未停止其他任务。CPU Code 的 CUDA 可见设备为空，OMP、MKL、OpenBLAS 均为 1 线程。环境文本参与 Code 哈希。
- 输入为共用真实 `1CRN.pdb`，A 链、4 条设计序列、batch_size=1、温度 0.1，保留分数及概率。正式矩阵原种子 44，来自此前调试后的独立缓存条件；不是按蛋白质效果选种子。正向筛选阈值 10.0、top_k=2，仅验证流程与排序；负向阈值 -1.0。换权重用已部署的真实 `v_48_030`。

## 决定与正确性边界

完整模型身份下，Computer UUID 不再区分同一模型部署；可执行路径、环境、模型身份、输入和参数仍进入原生指纹。身份未知时继续禁止缓存。CalcJob 缓存版本为 4，Parser 与清单校验规则未降低。

候选 UUID 统一指正式结果 `Dict`，⑤统一使用 `extras.ai4s_decision_records`。成员服务先查询，再通过原生 AiiDA 归档传入输入、计算和全部产物；不传 AuthInfo。接收端核对归档 SHA-256、模型、Code、输入、参数、正式端口和清单，再重建导入时清除的缓存哈希索引。C 直接消费结果；单任务使用原生缓存。单靠候选记录不得报告 R01。

## 命令与已执行检查

在专用环境中执行：

```bash
python -m pytest -q
python tests/test_engine_kernel.py
python tests/test_aiida_workflows.py
# 在统一内核源码根目录
python -m pytest -q -o addopts='' --broker-backend=zmq tests/engine/test_reuse.py
```

本地现有 `node --test tests/*.cjs` 六个测试文件通过。目标环境常规回归为 **111 passed、21 skipped**；21 项为需显式执行的 6 项原生检查与 15 项工作流检查，两组已分别执行通过。统一 fork 决策检查为 **15 passed**，有两条未安装 pytest-timeout 对应配置的警告，不影响该组结果。原生检查新增“候选未索引时不得报告 R01”拒绝用例。首次回归因同步遗漏说明和示例配置失败，补齐后暴露旧入口断言，已按 ckz 最新测试修正。

真实验证命令如下，token 与实际 peer 地址仅保存在运行目录的私有配置：

```bash
python scripts/verify_member_reuse.py \
  --config /home/coder/runs/integration-20261114/verify-config.json \
  --pdb /opt/ai4s/proteinmpnn/current/examples/1CRN.pdb \
  --seed 44 \
  --resume /home/coder/runs/integration-20261114/cross-member-05.json \
  --output /home/coder/runs/integration-20261114/cross-member-06.json
```

## 实际结果

最终[请求与状态矩阵](evidence/cross-member.json)、[独立原生核对及运行源码摘要](evidence/native-audit.json)、[归档传递回执](evidence/transfer-receipt.json)均已保存。七个过程均原生 finished、exit_status=0；每个请求可经 B 适配器读回唯一且合法的⑤记录。

| 场景 | 原生过程 UUID | 决定／理由 | 实际种子 | CalcJob 节点／模型执行 |
| --- | --- | --- | ---: | --- |
| csr 首次真实生成 | `39433984-ccad-42b5-8feb-0a9a69c2197e` | rerun／R03 | 44 | 1／1 |
| qhy 跨成员复用并筛选 | `3987e7bd-3c51-459e-8a85-3ac1f9604d0e` | reuse／R01 | 44 | 0／0 |
| qhy 原生缓存复用 | `f2d65bb3-6082-4232-b151-b857dfa27147` | reuse／R01 | 44 | 1／0 |
| 强制重算 | `0a8abca4-ce34-4b13-af98-47a15ba94487` | rerun／R03 | 44 | 1／1 |
| 新采样 | `ce2ba923-25b0-4713-83b0-3af48cffe2b0` | new_sample／R04 | 681281606 | 1／1 |
| 不合格候选排除 | `4bc1d841-f441-4dc1-9c71-02ac7653e869` | rerun／R02 | 44 | 1／1 |
| 切换真实权重 | `ec9bf806-2ed9-4a64-9eea-99a3c6f0971f` | rerun／R02 | 44 | 1／1 |

两阶段复用未创建 CalcJob；单任务新建的是缓存节点，缓存来源和远程工作目录均与 csr 源过程一致，没有再次执行模型。实际共五次模型执行，不能把六个 CalcJob 节点当成六次推理。

接收端和源端 Computer UUID 不同，但经过核实的 Code 哈希一致。归档导入保留源过程与结果 UUID，未挂载对方数据库；来源查询能沿原生链接找到 csr 的源过程。三个正式文件经两个 HTTP 服务下载逐字节相同，并与接收端 Repository 的 SHA-256 再次核对。独立按 `(score, sample_id)` 排序得到 s003、s004，与筛选输出一致。

阈值 -1.0 时，所有参与比较的候选均带 below_threshold 原因，决策降级重算；筛选结果为 0 条，不把过程正常结束解释为生物学合格。换成真实 v_48_030 后身份摘要和权重 SHA-256 改变，未复用旧结果。无 peer token 的跨容器请求返回 403。

最终矩阵使用原客户端编号恢复第五次的已完成源任务与筛选任务，二者没有重算；失败证据另存，最终文件不覆盖旧文件。所有执行源码与运行摘要逐文件一致；只有 B 模块 README 的后续说明更新与运行目录副本不同。

服务会话为 `ai4s-member-{qhy,csr}-v5-20261114`；矩阵会话 `ai4s-cross-member-v6-20261114` 已退出。宿主日志 cross-member-06.log、pytest-release.log、kernel-final-v2.log、workflows.log、fork-tests-v2.log 保留。原成员工作区 Git 状态复核与开始一致，未留下本轮模型进程。

## 调试与负面记录

- 首次 CPU 推理在 1 核容器内启动 112 个线程，5 分钟后仍未结束。只停止本轮创建的该任务，保留原生节点与 `cross-member-01.json`；重启服务导致该版验证器收到连接中断。后续显式限制 CPU 线程。
- 第二次验证在服务尚未就绪时连接失败，没有提交科学任务。验证入口已增加只读健康等待，不自动重试任务提交。
- 第三次运行的共享查询把普通字典传入要求 AiiDA `Dict` 的 C 校验器，HTTP 503 后降级重算，跨成员复用断言失败。已修正实际类型接口；没有删除门禁或把降级运行写成复用。
- 第四次两阶段跨成员复用通过，三个正式文件逐字节一致，未创建 CalcJob；单任务虽然记录 R01，但没有实际缓存来源，验证器拒绝通过。核对发现 AiiDA 归档导入清除了 `_aiida_hash`；增加校验后 rehash 与“无原生来源不得 R01”的检查，再执行第五次矩阵。
- 第五次源模型与跨成员筛选已完成，但状态接口在终态切换前读取报告，出现 finished 响应缺少 selection_report 的竞态。改为先确认终态再读取执行明细；第六次使用原客户端编号和上传引用恢复验证，没有重新运行前两个过程。
- 上述失败文件、日志和原生节点均保留，不覆盖为成功。因数据目录在已有挂载上沿用容器 root 身份，本轮归档解包使用 `--no-same-owner`；没有改动成员原 home 或共享环境所有权。fork 单测所需 Sphinx 只安装在本轮 qhy 专用环境。

## 当前限制

本轮验证目标是两个真实成员容器的 ProteinMPNN 结果共享与消费。没有重新验收所有成员组合、GPU、完整 RFdiffusion → ProteinMPNN → Boltz、真实模型中断恢复或完整实验 Agent 页面闭环。登记 UI 已整合，未新增真实 LLM 调用或浏览器视觉验收；既有成员应用入口与数据保持原状。

## PR 精简后的回归（2026-11-14）

以 `50ab095` 为基线，合并重复声明／决策文档，改为引用固定内核源码，删除旧三策略验证脚本与无行为校验价值的断言。业务源码、运行配置、依赖及本记录的证据 JSON 逐文件保持不变。同一请求的三策略与记录查询仍由 `tests/test_aiida_workflows.py::WorkflowIntegrationTests::test_three_reuse_policies_launch_only_when_required_and_persist_records` 覆盖，真实跨成员入口保留。

回归使用 `lab-gpu` 的 qhy 容器、既有专用 Python 3.12 环境，测试快照独立放在 `/home/coder/ai4s-pr11-cleanup-20261114`，未替换运行中的服务目录。命令为 `PYTHONPATH=src python -m pytest -q`，结果 **110 passed、21 skipped**；容器日志 `/home/coder/runs/integration-20261114/pr11-cleanup-pytest.log`（宿主 `/data1/qhy/runs/qhy/integration-20261114/pr11-cleanup-pytest.log`）。本地 `for test_file in tests/*.cjs; do node "$test_file" || exit 1; done` 的 6 个 JavaScript 测试文件、修改文档的相对链接与锚点检查、`git diff --check` 均通过。

21 个跳过项是单独执行的原生／工作流检查；这些入口、业务实现及内核未变，沿用本记录已有的 6 项原生、15 项工作流及 15 项 fork 检查证据。本次未重新运行科学任务、真实 LLM 或浏览器验收，不改写前述七个过程的结果。

返回：[引擎说明](../../docs/engine_service.md) · [状态](../../docs/status.md) · [仓库](../../README.md)。
