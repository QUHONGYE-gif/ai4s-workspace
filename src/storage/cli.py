"""命令行入口：run / lineage / runs / stats。

在 demo.py 的分步缓存引擎之上，补两个实用能力：
1. 处理任意 FASTA 文件（run），--force 显式选择"重新计算/重新采样"而不是复用；
2. 血缘查询（lineage）：看一个产物从哪来、被谁用、上游变更会影响哪些下游。

用法：
    python cli.py run data/test.fasta --user chensirui
    python cli.py run data/test.fasta --user chensirui --keep-gaps   # 改上游参数，只重算受影响步骤
    python cli.py run data/test.fasta --user chensirui --force       # 显式重新计算（如随机采样任务）
    python cli.py lineage                 # 全部产物与连线
    python cli.py lineage 5               # artifact #5 的来源与下游影响
    python cli.py runs                    # 执行历史
    python cli.py stats                   # 复用收益与存储占用
与 demo.py 共用同一个 .demo/ 数据目录，先跑 demo 再跑 cli 也能命中缓存。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from db import MetaDB
from pipeline import Executor, PIPELINE
from store import ObjectStore

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".demo"


def open_db() -> tuple[MetaDB, ObjectStore, Executor]:
    db = MetaDB(SANDBOX / "meta.sqlite")
    store = ObjectStore(SANDBOX / "store")
    ex = Executor(db, store, PIPELINE, "fasta_len_demo", "0.1.0")
    return db, store, ex


def kb(n: int | None) -> str:
    n = n or 0
    return f"{n / 1024:.1f} KB" if n >= 1024 else f"{n} B"


def print_run(results) -> None:
    for i, r in enumerate(results, 1):
        mark = "复用" if r.status == "reused" else "计算"
        print(f"   {i}. {r.name:<18} [{mark}] {r.duration_ms:6.2f} ms  {r.note}")


def resolve_input(raw: str) -> Path:
    """解析外部输入路径，兼容"工作目录不是脚本目录"的情况。

    编辑器里运行脚本时 cwd 往往落在项目根（例如 PyCharm 的 Misc 项目），
    直接按 cwd 解析 data/test.fasta 会找不到；这里先试 cwd，再退回脚本目录。
    """
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    for base in (Path.cwd(), HERE):
        cand = (base / p).resolve()
        if cand.exists():
            return cand
    return (Path.cwd() / p).resolve()


def cmd_run(args) -> int:
    db, store, ex = open_db()
    fasta = resolve_input(args.fasta)
    if not fasta.exists():
        print(f"错误：找不到文件 {args.fasta}", file=sys.stderr)
        print(f"  已尝试：{(Path.cwd() / args.fasta)}", file=sys.stderr)
        print(f"          {(HERE / args.fasta)}", file=sys.stderr)
        return 1
    overrides: dict[str, dict] = {}
    if args.digits != 1:
        overrides["length_stats"] = {"round_digits": args.digits}
    if args.keep_gaps:
        overrides["normalize_sequence"] = {"strip_gaps": False}

    intent = "强制重算（--force）" if args.force else "CLI 提交"
    run_id, results = ex.run(
        user_id=args.user,
        intent=intent + (f" | {fasta.name}" if intent == "CLI 提交" else ""),
        external_inputs={"fasta": fasta},
        overrides=overrides,
        force=args.force,
    )
    print(f"run #{run_id}  user={args.user}  输入={fasta.name}")
    print_run(results)
    stats_id = results[-1].artifact_ids.get("stats")
    if stats_id:
        art = db.get_artifact(stats_id)
        if store.exists(art["object_path"]):
            print(f"\n最终产物（artifact#{stats_id}, {kb(art['size_bytes'])}）：")
            print(store.get(art["object_path"]).decode("utf-8"))
    db.close()
    return 0


def cmd_lineage(args) -> int:
    db, store, _ = open_db()

    if args.artifact is None:
        rows = db.conn.execute("SELECT * FROM artifact ORDER BY id").fetchall()
        print("全部产物：")
        for a in rows:
            producers = [f"{r['name']}(step#{r['id']})" for r in db.producers_of(int(a["id"]))]
            consumers = [f"{r['name']}(step#{r['id']})" for r in db.consumers_of(int(a["id"]))]
            print(f"  #{a['id']:<3} {a['kind']:<14} {kb(a['size_bytes']):>8}  "
                  f"hash={a['content_hash'][:8]}…  policy={a['save_policy']}")
            print(f"      来源: {', '.join(producers) or '（外部输入）'}")
            print(f"      下游: {', '.join(consumers) or '（无）'}")
        db.close()
        return 0

    key = args.artifact
    row = None
    if key.isdigit():
        row = db.conn.execute("SELECT * FROM artifact WHERE id=?", (int(key),)).fetchone()
    if row is None:
        row = db.conn.execute(
            "SELECT * FROM artifact WHERE content_hash LIKE ?", (key + "%",)
        ).fetchone()
    if row is None:
        print(f"错误：找不到 artifact '{key}'", file=sys.stderr)
        return 1

    aid = int(row["id"])
    print(f"artifact#{aid}  kind={row['kind']}  {kb(row['size_bytes'])}  "
          f"hash={row['content_hash'][:12]}…  policy={row['save_policy']}")
    for r in db.producers_of(aid):
        print(f"  来源步骤: {r['name']} (step#{r['id']}, run#{r['run_id']}, {r['status']})")
    if not db.producers_of(aid):
        print("  来源步骤: （外部输入，policy=keep）")
    for r in db.consumers_of(aid):
        print(f"  下游步骤: {r['name']} (step#{r['id']}, 端口 {r['port']})")

    down = db.descendants(aid)
    print("\n影响分析：若该产物失效，下游将作废的产物：")
    if down:
        for did in down:
            a = db.get_artifact(did)
            print(f"  -> artifact#{a['id']:<3} {a['kind']:<14} {kb(a['size_bytes'])}")
    else:
        print("  （无下游，终端产物）")
    db.close()
    return 0


def cmd_runs(_args) -> int:
    db, _, _ = open_db()
    rows = db.history(limit=50)
    print(f"{'run':<6}{'状态':<9}{'计算':<6}{'复用':<6}{'用户':<12}意图")
    for row in rows:
        print(f"#{row['id']:<5}{row['status']:<9}{row['computed_count']:<6}"
              f"{row['reused_count']:<6}{row['user_id']:<12}{row['intent']}")
    db.close()
    return 0


def cmd_stats(_args) -> int:
    db, store, _ = open_db()
    st = db.reuse_stats()
    total = st["steps"] or 1
    print(f"步骤记录 {st['steps']} 条：计算 {st['computed']} / 复用 {st['reused']}"
          f"（复用率 {st['reused'] / total:.0%}）")
    print(f"累计计算 {st['compute_ms']:.2f} ms，命中缓存省下 {st['saved_ms']:.2f} ms")
    print(f"对象存储：{store.object_count()} 个 / {kb(store.total_bytes())}；"
          f"元数据库 {kb(db.disk_bytes())}")
    print(f"表行数：{db.table_counts()}")
    db.close()
    return 0


def no_args() -> int:
    """没有子命令时的兜底：有数据就展示概览，没数据就引导先跑 demo。

    编辑器里直接点运行（等价 python cli.py）走这里，而不是让 argparse 报错退出。
    """
    print("未指定子命令，默认显示复用统计（等价于 python cli.py stats）")
    print("可用子命令：run / lineage / runs / stats    完整用法见 python cli.py -h\n")
    if not (SANDBOX / "meta.sqlite").exists():
        print("当前还没有任何运行记录。先执行一次完整演示：python demo.py")
        return 0
    return cmd_stats(None)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI4S 后端存储 · 命令行入口")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="处理一个 FASTA 文件（自动复用缓存）")
    p.add_argument("fasta", type=str)
    p.add_argument("--user", default="demo-user", help="使用者 id，记入 run.user_id")
    p.add_argument("--force", action="store_true",
                   help="忽略缓存强制重算（对应随机任务的'重新采样'）")
    p.add_argument("--keep-gaps", action="store_true", help="规范化时不删除 gap 字符")
    p.add_argument("--digits", type=int, default=1, help="统计值小数位数（默认 1）")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("lineage", help="查看产物血缘；传 artifact id/哈希前缀做影响分析")
    p.add_argument("artifact", nargs="?", default=None)
    p.set_defaults(fn=cmd_lineage)

    p = sub.add_parser("runs", help="查看执行历史")
    p.set_defaults(fn=cmd_runs)

    p = sub.add_parser("stats", help="复用收益与存储占用")
    p.set_defaults(fn=cmd_stats)

    if len(sys.argv) == 1:          # 直接点运行、没给子命令
        return no_args()

    args = ap.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
