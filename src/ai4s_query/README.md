# AiiDA 查询与来源

在当前 profile 中只读查询运行状态、输入输出、Repository 文件和来源关系，支持文本、JSON 与工作台快照导出。读取文件不等于领域校验通过，产物资格仍由 [A](../../docs/aiida_tasks.md) 和 [C](../../README_C.md) 判断。

## 使用

使用已有 [AiiDA 环境](../../docs/environment.md)。模块随项目安装；直接从源码运行时，在仓库根目录设置 `PYTHONPATH=src`。

```bash
python -m ai4s_query.cli show <UUID或PK> --text report.txt --json report.json
python -m ai4s_query.cli tree <UUID或PK> --depth 5
python -m ai4s_query.cli trace <UUID或PK> --text trace.txt
python -m ai4s_query.cli cat <UUID> run.json
python -m ai4s_query.cli cat <UUID> scores/input.npz --out scores.npz
```

标识支持完整 UUID、至少 8 位的唯一 UUID 前缀或数字 PK。`show/tree` 查看原生输入、创建、返回和调用关系；`trace` 只选取一条主干，不代表完整工作流。

报告包含状态与失败诊断、参数值、节点哈希、逐文件 SHA-256 和读取入口。二进制文件可导出，不能按文本预览；缓存来源由 AiiDA 原生缓存属性查询，直接使用旧 Data 则沿输入链接追溯。

## 候选与实时查询

```bash
python -m ai4s_query.cli candidates --node <UUID> --profiles member-a,member-b
python -m ai4s_query.cli preflight --profiles member-a
python -m ai4s_query.cli decision <request_id或过程UUID>
python -m ai4s_query.cli serve --profile member-a --port 8848
```

独立服务提供 `/api/node/<UUID>`、`/api/trace/<UUID>`、`/api/candidates` 和 `/api/decision`。直接多 profile 查找只覆盖当前进程配置中可访问的数据库；实际跨容器查询与原生归档传递由[引擎服务](../../docs/engine_service.md#跨成员共享)连接。候选保留不合格原因；正式 ProteinMPNN 的 UUID 指结果清单，文件沿原生输出链接读取。

新决策与 C／内核共用 `extras.ai4s_decision_records`，可按请求或过程查询；旧单数键与旁路文件仅作历史兼容。`decision-write` 的节点写入同样通过 C 模块校验，不另设宽松的科学记录格式。

## 工作台快照

```bash
python -m ai4s_query.cli workbench <UUID> --out snapshot.json
# 保留已有页面记录时，先从页面导出，再追加
python -m ai4s_query.cli workbench <UUID> --base previous.json --out combined.json
```

通过页面“导入”读取，操作会替换当前浏览器记录。快照为只读离线数据，保留成功、失败、运行中和等待中状态；刷新网页不会查询引擎，需要重新导出。未记录的种子为 null，策略、归属及共享范围标为未记录。

JSON 只携带元数据，文件仍在来源 profile 的 Repository；页面文件访问关闭，使用 `cat` 读取实际内容。跨 profile 查看需先完成原生归档导入，不能把页面导入视为共享授权。

## 独立示例

```bash
PYTHONPATH=src python src/ai4s_query/examples/run_demo.py
```

示例在当前 profile 创建两步 calcfunction、共享输入、缓存、失败过程和通用二进制数据，不使用模型或 daemon。报告与 UUID 索引写入新的 `~/runs/query-demo-<时间戳>/`，可用 `--output <新目录>` 指定位置；失败过程是刻意生成的演示样本，二进制文件不是科学产物。

代码分工：`query.py` 查询原生节点与链接，`report.py` 格式化报告，`workbench.py` 映射离线快照，`cli.py` 提供命令行；`sample_calcs.py` 仅供示例使用。

返回：[仓库](../../README.md) · [工作台](../../web/README.md) · [当前状态](../../docs/status.md)。
