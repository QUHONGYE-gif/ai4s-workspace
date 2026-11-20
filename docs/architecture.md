# 项目架构（按现有代码与文档整理）

> 依据：`共用AiiDA引擎使用指南`、`coder使用共用模型指南`、`开发说明`、仓库 `src/` 与 `pyproject.toml` 入口点。
> 只描述现状，不包含尚未实现的跨成员复用。

## 1 三层结构

```
① 网页层（web/demo）            ② 引擎层（src/ai4s_engine）        ③ 执行层（AiiDA + 模型）
   工作台页面 / 引擎页面   ──HTTP──►  /api/engine/* 路由        ──►  个人 AiiDA profile
   assets/engine.js               声明、请求、决策、溯源             CalcJob → /opt/ai4s/*
                                                                    产物写 ~/runs 或输出目录
```

| 层 | 位置 | 职责 | 共享情况 |
| --- | --- | --- | --- |
| 网页 | `web/demo/` | 表单、状态、产物、来源展示 | 代码共享（Git） |
| 引擎 | `src/ai4s_engine/` | 路由、校验、决策记录、候选查询 | 代码共享，**进程每人一份** |
| 执行 | `~/.aiida` + `~/.venvs/aiida` | 提交 CalcJob、记录 provenance | **每人独立**，程序共享只读 |

## 2 代码包职责

| 包 | 职责 |
| --- | --- |
| `src/ai4s_engine` | HTTP 引擎：`/api/engine/{health,declarations,requests,decisions,archives,trace,nodes}` |
| `src/ai4s_tasks` | ProteinMPNN 的 CalcJob + Parser（入口点 `ai4s.proteinmpnn`）、`submit` 命令行 |
| `src/ai4s_workflows` | 两阶段工作流 `ai4s.protein-mpnn-filter`、轻量 CalcJob `ai4s.light-mpnn` |
| `src/ai4s_query` | 结果查询（站 9），供引擎与页面共用 |
| `src/ai4s_declarations` | 任务声明（约定①）读写 |
| `src/ai4s_demo` | Agent（实验页助手、声明助手）与 FastAPI 应用 |
| `src/workbench` | 工作台后端（静态资源、`/agent/*`、`/api/engine/*` 转发） |

## 3 一次真实任务的流转

1. 网页填参数 → `POST /api/engine/requests`（约定②结构，含 `reuse_policy`）
2. 引擎校验声明与参数 → 组装 CalcJob 输入 → `verdi` 提交到**个人 AiiDA profile**
3. AiiDA daemon 调 `proteinmpnn-8907e667@localhost`（指向 `/opt/ai4s/proteinmpnn/bin/proteinmpnn`，只读共享）
4. Parser 读 `outputs/`，校验 `run.json` 的 release（`8907e667-py312-torch260cu124`）
5. 产物落到节点：`artifacts.sequences/scores/probabilities`、`result`、`retrieved`
6. 页面轮询 `/api/engine/requests/{id}` 拿状态、产物、`cached_from`（复用来源）

## 4 运行前提（每台容器各做一次）

| 项 | 命令/位置 |
| --- | --- |
| 共用 AiiDA | `~/.venvs/aiida`，`verdi status` 显示 profile `ai4s` |
| daemon | `verdi daemon start 1`（工作区重启后需再起） |
| 注册 Code | `verdi code create core.code.installed ... proteinmpnn-8907e667` |
| 开启缓存 | `verdi config set caching.enabled_for 'aiida.calculations:ai4s.*'` |
| 项目插件 | `pip install -e .`（装进 aiida 环境，AiiDA 才能发现 `ai4s.*` 入口点） |
| 系统命令 | `ps`（procps），否则作业会被误判完成 |

## 5 共享与隔离边界

| 对象 | 共享 | 说明 |
| --- | --- | --- |
| 模型程序与权重 | ✅ 只读 | `/opt/ai4s/{proteinmpnn,rfdiffusion,boltz}` |
| GPU | ✅ 一张卡，串行 | 运行前 `nvidia-smi` 查看，与其他成员协调 |
| 代码 | ✅ Git | 各自 `dev-姓名首字母` 分支，PR 到 `main` |
| AiiDA profile | ❌ 独立 | 每人一个 `ai4s` profile，库在本人 home |
| 跨成员数据复用 | ❌ 待实现 | 同名 profile 不代表共用数据库 |

## 6 缓存（复用）的实际语义

- 触发条件：同 Code、同输入、同参数（CalcJob 缓存键），且入口点以 `ai4s.` 开头
- 命中表现：新进程仍会创建（新 PK），但 `cached_from` 指向原进程 UUID，**不重新计算**
- 实测：seed 42 → PK 5（`cached_from=None`）；同参数再跑 → PK 23，`cached_from=7c9e8c9b…`（PK 5 的 uuid）

## 7 当前边界

- 引擎服务要求 `aiida 2.9.4+ai4s.2`；共享环境是 `2.9.4`，所以 **HTTP 引擎层需要定制版本**，单独跑服务时才用得上
- 页面侧若直接读 AiiDA（`verdi`/`ai4s_query`），用共享 2.9.4 即可
- 模型环境（RFdiffusion/Boltz 的 conda）在负责人机器上，本容器没有；5.0 要评估的正是"能否重建/共用"
