# 存储层验证原型

AI4S 工作台后端存储的最小可运行验证：**读取 FASTA → 规范化序列 → 输出长度统计**。
目的是走通「存储 → 保存 → 记录 → 复用 → 影响分析」的完整链路，不是完整系统。

仅依赖 Python 3.11+ 标准库（sqlite3 / hashlib / json / pathlib / argparse / dataclasses），无第三方依赖。

## 运行

```bash
python demo.py          # 全流程演示（每次重建 .demo/，保证可复现）
python demo.py --keep   # 在已有库上继续累加
```

输出同时写入 `reports/demo_run.log`。`.demo/` 与 `reports/` 为本地运行产物，不纳入版本管理。

## 命令行

`cli.py` 与 `demo.py` 共用 `.demo/` 数据目录：

```bash
python cli.py run data/test.fasta --user <name>                  # 处理任意 FASTA，自动复用缓存
python cli.py run data/test.fasta --user <name> --keep-gaps      # 改上游参数，只重算受影响步骤
python cli.py run data/test.fasta --user <name> --digits 4       # 改下游参数，只重算末端步骤
python cli.py run data/test.fasta --user <name> --force          # 忽略缓存强制重算
python cli.py lineage                                            # 全部产物与血缘连线
python cli.py lineage <id>                                       # 指定产物的来源、下游与影响分析
python cli.py runs                                               # 执行历史（计算／复用计数）
python cli.py stats                                              # 复用率、节省耗时、存储占用
```

## 文件

| 文件 | 作用 |
| --- | --- |
| `store.py` | 内容寻址对象存储（`objects/<hash 前 2 位>/<sha256>`，临时文件 + 原子替换） |
| `db.py` | SQLite schema 与数据访问：5 张表、4 条索引、血缘与统计查询 |
| `pipeline.py` | 三个步骤的实现、步骤声明、缓存键计算、执行器 |
| `demo.py` | 6 个验证场景（冷启动／重跑／改名重交／改下游参数／改上游参数／清理后重算） |
| `cli.py` | 命令行入口：run / lineage / runs / stats |
| `data/test.fasta` | 示例输入，7 条记录，其中 1 条含非法残基用于验证剔除逻辑 |

## 数据落地位置

```text
.demo/
├── meta.sqlite     # 元数据：workflow / run / step / artifact / step_io
└── store/objects/  # payload，按 sha256 存放，同一内容只存一份
```

## 核心机制

`cache_key = sha256(步骤名, 步骤版本, 参数, 各输入端口的内容哈希)`——同样的输入与参数跨执行命中缓存；上游一变，下游 cache_key 自动全变，只重算受影响分支。命中后还要再确认产物文件仍然存在，否则降级为重算。
