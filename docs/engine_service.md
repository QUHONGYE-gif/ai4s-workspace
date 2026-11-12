# 真实任务引擎服务

本模块接通 ProteinMPNN 单任务，以及 ProteinMPNN → 筛选。工作台使用标准库 HTTP 转发，AiiDA 与模型依赖留在独立引擎环境。真实执行、请求与原生节点的对应关系见 [R006 记录](../experiments/R006-aiida-engine/record.md)，当前能力见 [状态](status.md)。

## 契约与代码来源

接口以飞书任务 4.0 已发布版本为准：[①任务声明](https://lcnzinmktf6r.feishu.cn/wiki/Bi2fwF5GNiihDEkC2g3ctCz0nlb)、[②提交与状态](https://lcnzinmktf6r.feishu.cn/wiki/QvU9w2VMIiUeKPkZT4KceCiAnHf)、[③模型身份](https://lcnzinmktf6r.feishu.cn/wiki/Sc5kw5A1BiAuNIk7kEgcVMPVnZd)、[④候选结果](https://lcnzinmktf6r.feishu.cn/wiki/YH74w7cq6iZLdVkpVBBcMEtcnlc)、[⑤决策记录](https://lcnzinmktf6r.feishu.cn/wiki/WRgGwqdcKiqvFNkwqSscY7pMn8c)。没有把声明、模型或策略判断交给浏览器或 LLM。

本次选择性复用以下交付，没有整体合并成员旧页面。

| 来源 | 固定提交 | 本次使用 |
| --- | --- | --- |
| `dev-ckz` | `26f8257f6cb101ecdf4257b4858f462af5f189de` | 声明 registry、真实 ProteinMPNN 声明与参数检查 |
| `dev-wyh` | `f5b09576d89fd75c4be9105f3fa8ee38f9984ae9` | C WorkChain、持久化决策、重试与恢复逻辑；[模块说明](../README_C.md) |
| `dev-csr` | `8fecc5f1bbd3056bb8a3bc815abe53d1422dc0c8` | 候选构造与合格判定；⑤查询直接读取 C 与内核选择点共用的 extras 记录 |

②由 [service.py](../src/ai4s_engine/service.py) 实施；③由 [identity.py](../src/ai4s_engine/identity.py) 与内核共同实施；[decisions.py](../src/ai4s_engine/decisions.py) 把原生缓存选择接到成员的④⑤实现。两阶段任务继续由 C 决策和运行，返回原生 WorkChain UUID。单任务在内核缓存选择点保存⑤，返回本次新建 CalcJob UUID。

## 内核位置与改动

- 团队 fork：[QUHONGYE-gif/aiida-core](https://github.com/QUHONGYE-gif/aiida-core)，版本标签 `ai4s-2.9.4-1`，提交 `88f20d639f16884f4df9afd97cf2011aecb79e53`。
- 上游基线：`v2.9.4`／`9ffe5ed8220e59b20d2d5f2d79ecb3410488cd06`。安装后 Python 版本标识为 `2.9.4+ai4s.1`。
- [完整补丁](../patches/aiida-core-2.9.4-ai4s.patch)可对固定上游源码应用；没有修改团队原共用版本或个人 profile，也没有推送两个仓库的 `main`。

| 原生位置 | 改动与作用 |
| --- | --- |
| `orm/nodes/data/code/abstract.py` 的 `AbstractCode` | 提供不可变 `model_identity` 属性，校验六个字段；属性进入原生 Code 哈希 |
| `engine/processes/calcjobs/calcjob.py` 的 `CalcJob.define/_setup_metadata/_setup_inputs` | 接收不进入科学指纹的请求上下文；缓存查找前复制 Code 身份到计算属性，写入身份摘要；保留身份未知原因 |
| `orm/nodes/process/calculation/calcjob.py` 的 `CalcJobNodeCaching` | 有上下文时调用受信任配置的选择函数；身份未知时不读缓存、也不成为缓存来源；选择结果必须属于原生合格候选；没有 AI4S 上下文时沿用原生行为 |
| `aiida/__init__.py` | 独立版本标识 |

`AIIDA_AI4S_CACHE_DECISION=ai4s_engine.decisions:select_cache` 由服务端部署配置提供，不能从 HTTP 请求指定 Python 导入路径。没有配置扩展点的 AI4S 请求会明确失败，不能静默变成首次命中即复用。

模型身份从实际 `current` 与 manifest 读取，并复算权重文件 SHA-256。参数先补齐全部默认值。模型名、权重、源码提交、release 影响 Code／计算指纹，种子留在参数中。发布正式产物前，A Parser 再比较实际 `run.json` 的 release、源码提交与权重 SHA-256。Parser 和 CalcJob 的缓存版本为 3；旧校验结果不会混用。[A 原有检查](aiida_tasks.md)继续保留。

## 独立安装与启动

使用 Python 3.12，复用项目现有 AiiDA 2.9.4 依赖。先把 fork 的固定标签解压／检出到独立源码目录，另建专用 venv；在该 venv 的 `site-packages` 中用 `.pth` 引用固定 fork 的 `src`、本项目的 `src` 和已有只读 AiiDA 依赖目录。插件 entry point 沿用 [pyproject.toml](../pyproject.toml)，也可在具备构建依赖的独立环境执行 `python -m pip install --no-deps -e .`。不要覆盖原共享 aiida 包或复用原 `AIIDA_PATH`。

下面的环境与数据路径由操作者指定，均应是新建的专用位置。首次用 `verdi presto --non-interactive --use-zeromq --profile-name ai4s-engine --email <本人邮箱>` 创建独立 profile，并配置它的 `localhost` 工作目录。科学程序入口仍使用目标环境已有的 `/usr/local/bin/proteinmpnn`。

```bash
export AIIDA_PATH=/专用配置根目录
export AIIDA_AI4S_CACHE_DECISION=ai4s_engine.decisions:select_cache
# 只有需要 CPU 验证时设置；模型身份仍由真实部署解析。
export AI4S_ENGINE_DEVICE=cpu
cd /本项目目录
/独立环境/bin/python -m aiida -p ai4s-engine daemon start 1
/独立环境/bin/python -m ai4s_engine.server \
  --profile ai4s-engine --port 3003 --data-dir /专用请求目录
```

服务默认只监听回环；运行前用健康接口确认版本与 daemon。原工作台启动方式保持不变，其 `/api/engine/` 通过标准库转发到回环 3003；`AI4S_ENGINE_PORT` 仅用于服务端配置固定目标端口。页面入口为 `engine.html`，也可从工作台侧栏进入“真实实验”。

```bash
curl http://127.0.0.1:3003/api/engine/health
# 通过工作台代理时，将 3003 替换为工作台 HTTP 端口。
```

## 使用与查询

1. `POST /api/engine/uploads`，JSON 为 `filename` 和 PDB 文本 `content`；响应包含 `upload_id`、SHA-256 和大小。上传不超过 1 MiB，不接收客户端任意文件路径。
2. 按②提交请求。`declaration` 使用 `proteinmpnn`／`1`，`workflow` 使用 `single` 或 `mpnn_filter`；请求者保留账号和姓名。
3. 轮询请求状态；以 `finished` 或 `failed` 为终态。`client_ref` 在同一成员范围防重，相同编号携带不同正文会被拒绝，服务重启后仍保留记录。未知提交状态不会自动重跑。
4. 查看决策、来源与正式文件。

| 接口 | 用途 |
| --- | --- |
| `GET /api/engine/declarations/proteinmpnn/1` | 从服务端获取已校验声明，供参数表单使用 |
| `POST /api/engine/requests` | 按②提交，HTTP 202 返回状态对象；提交前检查失败也带请求编号和失败原因 |
| `GET /api/engine/requests/{request_id}` | 原生过程、实际种子、身份、缓存来源与输出 UUID |
| `GET /api/engine/decisions?request_id=…` | 完整⑤记录，读取 C 与内核选择点的同一个 extras 载体 |
| `GET /api/engine/nodes/{uuid}` | B 模块的实时原生来源描述 |
| `GET /api/engine/files/{uuid}` | 下载原生 `SinglefileData` |

本轮的请求、状态、完整候选和决策示例直接来自 [R006 证据目录](../experiments/R006-aiida-engine/evidence/)。上传编号与 UUID 属于当时独立 profile，迁移环境时须先上传自己的输入；不能把这些实例标识当作通用常量。

## 当前集成边界

本服务的实际候选范围是所配置的独立 profile。已接入 B 的候选字段和 C 的决策逻辑，保留产出者姓名。B 的多 profile 查找函数仍在，服务没有自动挂载其他成员的私有数据库，也没有将跨 profile 返回的 UUID 直接冒充本库可复用节点。真实跨容器查询、数据传入及复用需与陈思睿的共享方案继续联调；本轮不宣称多人共享已通过。

请求者字段用于原型归属记录，不代替真实成员鉴权。登记页与实验 Agent 仍沿用各自已有原型；本次增加显式真实实验入口，没有把模拟实验按钮整体改成科学任务提交。全员最终集成与 `main` 合并仍按[会议流程](collaboration.md#汇总会议与合并)处理。

验证命令与实际结果见 R006。独立内核检查使用 `python tests/test_engine_kernel.py` 创建一次性 profile，不会操作个人数据库。按照用户要求，本轮未执行浏览器验收；页面视觉、上传点击与浏览器轮询不能由 API 检查替代。

返回：[状态](status.md) · [工作台](../web/README.md) · [运行要求](environment.md) · [仓库](../README.md)。
