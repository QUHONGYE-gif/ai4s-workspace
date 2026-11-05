# 演示脚本（汇报用）

只用 AiiDA 原生 `calcfunction`，不依赖 ProteinMPNN 插件、Code 注册或 daemon，
因此可以独立运行与演示。真实模型的节点就绪后，把同一套命令的入参换成真实 UUID 即可。

## 0. 准备（每个新终端执行一次）

```bash
cd ~/ai4s-workspace
export PYTHONPATH=$PWD/src
PY=~/.venvs/aiida/bin/python
verdi status            # 确认 profile 为 ai4s
```

## 1. 一键造节点 + 出报告

```bash
PYTHONPATH=src $PY src/ai4s_query/examples/run_demo.py
```

产出目录：`~/runs/query-demo-<时间戳>/`

| 文件 | 演示什么 |
|---|---|
| `01-trace-完整轨迹.txt` | 一条竖线看完整条链：序列 → 统计 → 字典 → 筛选 → 布尔结果 |
| `02-show-过程详情.txt` | 单节点：状态、参数值、产物、校验哈希 |
| `03-show-缓存命中.txt` | 缓存命中（过程没执行）+ 来源 UUID |
| `04-show-失败诊断.txt` | 失败节点：`process_state=excepted` + 异常原文 |
| `05-show-数据复用.txt` | 同一 Data 被两个下游使用（数据级复用） |
| `00-索引.txt` | 每条报告对应的 UUID |

注意：`ai4s` profile 上第一次运行时是真实执行；重复运行会出现「缓存命中」，
这是正常现象，正好用于第 4 幕的对照。

## 2. 六幕演示

| 幕 | 命令 | 一句话 |
|---|---|---|
| 1 | `verdi status` | AiiDA 2.9.4、profile ai4s、ZeroMQ broker，环境可复现 |
| 2 | `$PY -m ai4s_query.cli trace <UUID>` | 一条命令看完整条链，从输入到产物 |
| 3 | `$PY -m ai4s_query.cli show <UUID>` | 展开参数值、退出码、校验哈希 |
| 4 | 看 `02` 的「缺失与不可读」段 | 这些分类不是编的，是真实缺失 |
| 5 | 对比 `02` 与 `03` | 这条缓存命中（没执行），这条是真实执行 |
| 6 | `$PY -m ai4s_query.cli cat <UUID> source_file` | 产物读取入口，一行命令打开文件 |

`show` 支持完整 UUID、≥8 位前缀、数字 PK 三种写法。

## 3. 三个容易踩的点

1. **必须 `PYTHONPATH=$PWD/src`**，否则 `No module named ai4s_query`；
2. **解释器是 `~/.venvs/aiida/bin/python`**，不是系统 `python`
   （`/usr/local/bin/verdi` 只是指向它的 shell 包装）；
3. **UUID 现场用 8 位前缀**，写进文档用完整值。

## 4. 真实模型接入后要改的两处

| 位置 | 现在 | 接真实节点后 |
|---|---|---|
| 产物解析 | 读 `Dict` 与仓库文件 | 读 `run.json` / `seqs/*.fa` / `scores/*.npz` |
| 筛选判据 | `length >= min_len` | `global_score` 升序取前 N（分数越低越好） |

查询、轨迹、报告三层不用改。
