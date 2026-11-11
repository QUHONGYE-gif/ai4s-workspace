# ai4s_query —— 运行结果与来源查询

给定一个运行节点或结果节点的 UUID（或 PK），输出它的运行状态、输入与参数、产物与校验记录、
血缘关系与缺失信息，支持 JSON 与可读报告两种导出。

对应四点能力：

1. **状态查询**：运行状态、成败原因、输入输出、父子过程、产物清单、校验记录与文件读取入口
2. **血缘反查**：从筛选结果 → ProteinMPNN 过程 → 输入 PDB；从设计序列 → 后续使用它的筛选任务
3. **报告导出**：JSON + 可读报告，区分「正式产物 / 失败诊断 / 未记录信息 / 不可读文件」
4. **复用区分**：缓存命中复用（过程级）与直接复用旧 Data（数据级）

任务 4.0 追加两项能力（站 5、站 9）：

5. **跨成员候选查找**：按计算指纹在多个 profile 之间查候选，输出约定④ 的字段与不合格原因
6. **实时查询接口**：只读 HTTP 服务，网页按 UUID 读来源、产物与约定⑤ 决策记录
7. **接入就绪**：读取与节点类型无关（calcfunction 与 CalcJob 同一套）；`preflight` 逐条体检节点；
   `decision-write` 校验后写决策记录。见 [接入就绪-站5站9](../../docs/接入就绪-站5站9.md)

说明见 [任务 4.0 · 跨成员候选查找与查询接口](../../docs/task4-candidates-and-query-api.md)。

## 目录

```
src/ai4s_query/
├── __init__.py
├── sample_calcs.py    # 原生两步样例（seq_stats -> filter_by_length）+ 故意失败样例
├── query.py           # 核心：节点描述、校验记录、血缘、四分类缺失信息
├── report.py          # JSON / 可读报告导出
├── candidates.py      # 跨成员候选查找（约定④：字段、五级判定、六种原因）
├── decision.py        # 约定⑤ 决策记录的读取、校验与写入（适配层）
├── server.py          # 只读查询服务（/api/node、/api/trace、/api/candidates、/api/decision）
├── members.json       # profile -> 成员姓名 映射（跨库场景下唯一的「人」来源）
├── cli.py             # 命令行入口（show / trace / tree / cat / workbench / candidates / decision / serve）
├── workbench.py       # 导出为「研序」工作台可导入的记录 JSON
├── DEMO.md            # 演示脚本（汇报用，六幕）
└── examples/
    ├── run_demo.py                # 一键：造四类节点 + 生成全部报告
    ├── run_two_step.py            # 两步样例 + 演示「直接复用旧 Data」
    ├── run_cache_demo.py          # 演示「缓存命中复用」
    ├── run_failure_case.py        # 生成失败节点 + 二进制产物节点（四分类真实样本）
    ├── run_task4_demo.py          # 任务 4.0 一站演示：跨成员候选 + 不合格组 + 决策记录
    ├── run_calcjob_shape_demo.py  # 接入就绪：CalcJob 形状产物 + 决策写入 + 体检
    └── make_sample_decision.py    # 由真实候选生成一条约定⑤ 决策记录（联调期用）
```

## 运行

模块只依赖 `aiida-core`，不需要额外安装，把 `src` 加入 `PYTHONPATH` 即可：

```bash
cd <仓库根目录>
export PYTHONPATH=$PWD/src
python -m ai4s_query.cli --help
```

先跑样例产生数据（任意一项即可，需在已配置 profile 的 AiiDA 环境中）：

```bash
python src/ai4s_query/examples/run_demo.py           # 一键：四类节点 + 全部报告
python src/ai4s_query/examples/run_two_step.py       # 两步计算 + 直接复用旧 Data
python src/ai4s_query/examples/run_cache_demo.py     # 缓存命中对比
python src/ai4s_query/examples/run_failure_case.py   # 失败节点 + 二进制产物
```

查询：

```bash
# 可读报告
python -m ai4s_query.cli show <UUID或PK> --text 报告.txt

# 机器可读
python -m ai4s_query.cli show <UUID或PK> --json 报告.json

# 主干轨迹：输入 → 计算 → 产物，一条竖线看完
python -m ai4s_query.cli trace <UUID或PK> --text 轨迹.txt

# 血缘树（上下游）
python -m ai4s_query.cli tree <UUID或PK> --depth 5

# 文件读取入口：文本直接打印，二进制用 --out 导出
python -m ai4s_query.cli cat <UUID> run.json
python -m ai4s_query.cli cat <UUID> scores/1CRN.npz --out 1CRN.npz
```

### 跨成员候选查找（站 5）

```bash
# 以某个结果节点为参照，按它的指纹在所有 profile 里找候选
python -m ai4s_query.cli candidates --node <UUID或PK>

# 直接用指纹（支持前 16 位前缀）
python -m ai4s_query.cli candidates --fingerprint 2a20461daa76ff27

# 带质量门限：要求 4 条序列、最优分数不高于 1.2
python -m ai4s_query.cli candidates --node <UUID> --num-sequences 4 --score-threshold 1.2

# 只列合格候选（默认也列不合格的，带原因）
python -m ai4s_query.cli candidates --node <UUID> --qualified-only

# 限定 profile，导出 JSON
python -m ai4s_query.cli candidates --node <UUID> --profiles lab,lab2 --json 候选.json
```

成员姓名来自 `members.json`（`{"profile名": "姓名"}`），也可用环境变量
`AI4S_MEMBERS='{"lab":"陈思睿"}'` 覆盖。

### 查询服务（站 9）

```bash
python -m ai4s_query.cli serve --port 8848          # 或 python -m ai4s_query.server
curl localhost:8848/api/health
curl localhost:8848/api/node/<UUID>
curl localhost:8848/api/candidates?fingerprint=<指纹前缀>
curl localhost:8848/api/decision?request_id=<请求编号>
```

## 实现约定

- **不使用 QueryBuilder 的 `has_key` / `contains`**（SQLite profile 不支持）；
  节点查找只用 uuid 等值 / like 前缀查询，血缘遍历用 ORM 链接 API。
- 节点识别支持：完整 UUID、UUID 前缀（≥8 位）、数字 PK。
- **链接方向**：数据被过程使用走 `input_calc` / `input_work`；
  `create` 只出现在「过程 → 输出数据」方向，`return` 用于工作流返回值。
  报告中的下游关系因此标注为 `used_by` / `produced` / `calls`。
- **校验记录**：节点级 `node.base.caching.get_hash()`；文件级对每个仓库文件算 sha256。
  两类都写入报告，便于与 ProteinMPNN 的 `run.json` 内哈希对照。
- **四分类判定**：

  | 类别 | 判定规则 |
  | --- | --- |
  | 正式产物 | 仓库文件可读（text） |
  | 失败诊断 | `process_state in (excepted, killed)` 或 `exit_code != 0`，附日志尾部 |
  | 未记录信息 | 无 creator（来源不可考）、无输入、CalcJob 缺 parameters、过程未结束 |
  | 不可读文件 | 读取抛异常，或二进制（不可按文本读，可导出） |

- 缓存判定：`is_created_from_cache` + `get_cache_source()`（extras 的 `_aiida_cached_from`）。
- **参数内联**：报告与轨迹里直接显示实际值（`Dict` 展开、`Int/Float/Str/Bool` 取值、
  文件类给出文件名 + 大小 + sha256），避免只看到 UUID。
- **工作台导出**：`workbench` 子命令把轨迹映射为研序的实验记录 JSON
  （产物带 `provenance.uuid` 与逐文件 sha256；过程步骤标注「真实执行」或「缓存命中」）。
  只生成文件，不改动 `web/` 下任何代码；导入会替换研序当前记录，可用 `--base` 追加。

## 已知限制

- 只读查询，不修改任何节点。
- 各人容器的 profile 数据库独立，联合查看需在同一 profile 中运行，
  跨容器需 `verdi archive export/import`。
- 真实 ProteinMPNN CalcJob 的产物（`run.json` / `seqs/*.fa` / `scores/*.npz`）解析
  待执行侧接口就绪后接入；`retrieve_list` 决定报告能看到哪些文件。
- 当前样例为 `calcfunction` 节点，用于验证查询逻辑；缓存命中的真实演示依赖已注册的 Code。
