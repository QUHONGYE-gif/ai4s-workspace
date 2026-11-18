# R006：任务 4.0 模型身份与真实引擎服务

状态：本人模块的实现和 API／原生节点验收完成。全员最终集成、真实跨容器共享与会议合并未完成。本记录不构成蛋白质设计质量或性能评测。

日期：2026-11-12（Asia/Taipei）。依据：[飞书任务 4.0](https://lcnzinmktf6r.feishu.cn/wiki/GP9iwzUhJijmjckMdHmczRqsnPc)，周期 11 月 7—12 日。曲鸿烨负责模型身份指纹、独立引擎服务、②③以及协议审阅和集成。

## 环境、代码与输入

- 运行位置：项目 `lab-gpu` 的本人 Coder 容器 `ai4s-personal-qhy-dev`。独立 Python 3.12.15；AiiDA `2.9.4+ai4s.1`，SQLite + ZeroMQ，daemon 1 worker。现有共享 2.9.4、本人原 `ai4s` profile、Agent 和 PyMOL 进程均保留。
- 共享 GPU 在检查时忙碌，本轮设置 `AI4S_ENGINE_DEVICE=cpu`，Code 使用 `CUDA_VISIBLE_DEVICES=""`；未运行新的 GPU 任务。
- 工作台基线：`dev-qhy@353e3ad`；成员来源固定提交见[服务说明](../../docs/engine_service.md)。模型执行时保留了实际源码快照与补丁；最终修订只修复状态读取、完成时间和输入边界，不改写既有计算。
- 内核：上游 `9ffe5ed8220e59b20d2d5f2d79ecb3410488cd06`，团队 fork 提交 `88f20d639f16884f4df9afd97cf2011aecb79e53`，标签 `ai4s-2.9.4-1`。改动位置、补丁与启动方式只在服务说明维护。
- 输入：共用模型版本目录中的真实 `examples/1CRN.pdb`，A 链，4 条设计序列，`batch_size=1`，温度 0.1，原种子 41，保存分数和概率。筛选阈值 10.0、`top_k=2`；宽阈值只用于检查流程与排序，不能作为科研质量标准。
- 权重：官方 `v_48_020` 与 `v_48_030`，SHA-256、源码提交与实际指纹见 [native-calculations.json](evidence/native-calculations.json)。运行前复算权重 SHA-256，Parser 再核对运行后身份。

## 实际结果

下表的 PK 只在本轮独立 profile 中有效。完整请求／过程 UUID、状态、输出和理由见 [matrix-status.json](evidence/matrix-status.json)；完成时间修正及服务重载后的最终回读另存为 [final-status.json](evidence/final-status.json)，实际提交正文见 [request-payloads.json](evidence/request-payloads.json)。

| 场景 | 原生过程 PK | 结果 | 实际种子 |
| --- | --- | --- | --- |
| 首次允许复用 | 4 | 无候选，R02，真实执行成功 | 41 |
| 同参再次请求 | 13 | R01，原生缓存来源为 PK 4 | 41 |
| 显式补齐默认值 | 22 | 与省略默认值的请求指纹相同，复用 PK 4 | 41 |
| 强制重算 | 31 | R03，无缓存来源，建立新执行工作目录 | 41 |
| 新采样 | 40 | R04，无缓存来源，建立新执行工作目录 | 2055269585 |
| 换成真实 `v_48_030` | 50 | 模型摘要从 `865635b5e489a115…` 变成 `35cf1ef74f9fbcdf…`，指纹改变，真实执行成功 | 41 |
| 两阶段流程 | WorkChain 64 | 复用首次模型结果；不新建 CalcJob；执行筛选后返回 2 条 | 41 |

6 个 CalcJob 对应 4 个实际模型执行目录；两个缓存节点仍指向首次执行目录。两阶段 C 报告记录 `attempt_count=0`、`calcjob_submissions=0`、`model_launches=0`。该计数与原生调用链接、缓存来源及工作目录一起核对，没有把 CalcJob 节点数直接当作模型启动次数。

候选 `elapsed_s` 沿用 B 模块的原生过程时间差，包含调度与解析开销，本轮没有将其当作纯模型耗时或用于成本结论。

三个文件端口均可经 HTTP 下载，包含 FASTA、分数 NPZ 和概率 NPZ。Parser 的原有序列／分数／概率检查全部通过。独立按 `(score, sample_id)` 排序得到 `s004、s001`，与 C 输出一致；真实分数为 0.7742 与 0.7778，见 [filter-verification.json](evidence/filter-verification.json)。

每种策略均可按请求编号读到完整⑤。样例保留完整④字段，并绑定实际过程 UUID。防重检查确认同一成员、同一 `client_ref` 不创建第二个请求；相同编号携带不同内容返回 HTTP 400。零种子、错误声明版本、缺失上传与非法请求者在提交前返回失败，`process=null`；见 [negative-checks.json](evidence/negative-checks.json)。

## 验证

- 本地 Python 3.11：身份摘要的已发布固定向量、实际权重内容核对、A 参数／产物与工作台 HTTP 共 16 项通过；首次 HTTP 检查受本地沙箱端口限制，获准回环端口后同组通过。
- 目标独立 AiiDA 环境：上述检查加成员的纯决策测试，共 37 项通过。
- `python tests/test_engine_kernel.py`：4 项独立临时 profile 检查通过。验证同身份相同指纹、版本／权重／种子变化影响指纹、身份未知时不读／不提供缓存、Parser 对源码和权重变化分别返回 302／303。这些为合成拒绝用例，没有冒充真实模型结果。
- 最终目标环境全量 Python 回归为 83 passed、14 skipped；跳过项包括需单独启动的临时 profile 检查，4 项内核检查已按独立命令另行通过。6 个现有 JavaScript 测试文件、JS 语法及相对文档链接检查通过。用户明确不需要浏览器验收，因此未将页面视觉或点击交互记为通过。

首次内核测试误用了需要 broker 的默认 Runner，4 项均因临时 profile 未启动 broker 失败；改为不执行作业的无 broker Runner 后全部通过。独立环境首次初始化也被 macOS 归档附带的 AppleDouble 文件阻断；仅清理新建副本中的该元数据后成功，原始环境未改动。

两阶段计算首次已成功，但状态接口把 AiiDA `NodeLinksManager` 当作普通字典调用 `.items()`，返回 503；修复为读取原生输出链接后，回读同一 WorkChain 成功，没有重新计算。服务重载时发现 `docker exec` 内进程未随外层 tmux 中断退出，核对 PID 与专用数据目录后只重启了本轮创建的服务。

## 产物与操作位置

- 容器专用代码：`/home/coder/ai4s-engine-workspace`。
- 容器专用环境：`/home/coder/.venvs/aiida-engine`。
- 容器配置根：`/home/coder/runs/engine-20261112/config`；新 profile 为 `ai4s-engine`。
- 服务、模型工作目录和证据根：容器 `/home/coder/runs/engine-20261112/`，宿主机 `/data1/qhy/runs/qhy/engine-20261112/`。
- tmux：`ai4s-engine-20261112` 和 `ai4s-engine-web-20261112`。日志为 `engine.log`、`workbench-proxy.log`；启动包装为该目录的 `engine-env.sh`。
- 本次个人预览保留原工作台 3001，通过专用标准库工作台进程 3011 转发 `/api/engine/` 到 3003；Nginx 仅热重载新增路由。原路由与导航快照保留在上述结果目录。更新后的完整仓库可直接由原 3001 后端转发，无需永久保留两份工作台进程。
- 个人预览增加 `engine.html` 入口；健康、声明、状态、来源和文件端点均从原 3000 入口验证。未覆盖原 `app.js`、既有 1CRN 文件或模型密钥。

## 尚未通过的验收

没有证明跨成员真实容器结果能实时查到并复用。共享方案必须继续按陈思睿的交付联调，不把相同成员名、UUID 字符串或本库复用代替跨库证据。也未将所有登记／实验 Agent 页面整合到真实执行入口，未运行完整 RFdiffusion → ProteinMPNN → Boltz，未合并 `main`。五份协议已核对正文，但“资料齐全”不等于全员接口验收通过。

返回：[引擎说明](../../docs/engine_service.md) · [当前状态](../../docs/status.md) · [实验目录](../)。
