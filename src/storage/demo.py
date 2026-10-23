"""演示脚本：把"存储 → 保存 → 记录 → 复用"整条链路跑给人看。

运行：
    python demo.py            # 全流程演示，输出到控制台 + reports/demo_run.log
    python demo.py --keep     # 保留上一次的 .demo 目录（默认每次重建，保证可复现）

演示的 8 个场景，正好对应汇报里要回答的问题：
    1. 库里有什么（表结构 / 元数据字段）
    2. 冷启动跑一次，写了哪些记录
    3. 原样重跑 → 全命中（缓存怎么生效）
    4. 输入换个文件名再交 → 仍然命中（内容寻址，不看文件名）
    5. 只改下游参数 → 只重算下游（依赖传播）
    6. 只改上游参数 → 下游全部重算
    7. 产物按策略清理后再跑 → 缓存失效、自动重算（保存 vs 重算的边界）
    8. 影响分析 + 复用收益 + 存储占用
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from db import MetaDB
from pipeline import Executor, PIPELINE
from store import ObjectStore

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".demo"
FASTA = HERE / "data" / "test.fasta"
LOG = HERE / "reports" / "demo_run.log"

USER = "chensirui"
WORKFLOW = ("fasta_len_demo", "0.1.0")


class Printer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def kb(n: int) -> str:
    return f"{n / 1024:.1f} KB" if n >= 1024 else f"{n} B"


def show_run(p: Printer, tag: str, run_id: int, results) -> None:
    p(f"\n[{tag}] run #{run_id}  user={USER}")
    for i, r in enumerate(results, 1):
        mark = "复用" if r.status == "reused" else "计算"
        p(f"   {i}. {r.name:<18} [{mark}] {r.duration_ms:6.2f} ms")
        p(f"      {r.note}")
        p(f"      产物: " + ", ".join(f"{k}=artifact#{v}" for k, v in r.artifact_ids.items()))


def main() -> int:
    if "--keep" not in sys.argv:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.mkdir(parents=True, exist_ok=True)

    db = MetaDB(SANDBOX / "meta.sqlite")
    store = ObjectStore(SANDBOX / "store")
    ex = Executor(db, store, PIPELINE, *WORKFLOW)
    p = Printer()

    p("=" * 78)
    p("AI4S 工作台 · 后端存储最小验证  |  读取 FASTA → 规范化序列 → 长度统计")
    p("=" * 78)

    # ---------- 1 ----------
    p("\n【1】库里存了什么")
    counts = db.table_counts()
    p("  表 / 行数：" + "  ".join(f"{k}={v}" for k, v in counts.items()))
    p("  元数据字段映射：")
    p("    工作流      -> workflow(name, version, code_digest)")
    p("    修改时间    -> run.started_at / step.created_at / artifact.created_at")
    p("    对应参数    -> step.params_json")
    p("    模型        -> step.task_version（真实项目里放权重文件摘要）")
    p("    产物        -> artifact(content_hash, object_path, size_bytes) + step_io")
    p("    使用者 id   -> run.user_id")
    p("    使用策略    -> artifact.save_policy（keep / cache / meta_only）")
    p("    历史记录    -> step 只追加不更新，status=reused/computed 都是历史")

    # ---------- 2 ----------
    p("\n【2】冷启动：第一次跑，三步全部真实计算")
    rid, res = ex.run(user_id=USER, intent="首次跑通 FASTA 小流程",
                      external_inputs={"fasta": FASTA})
    show_run(p, "冷启动", rid, res)
    p("  写入记录：run 1 条 + step 3 条 + artifact 4 个（含原始输入）+ step_io 6 条")

    # ---------- 3 ----------
    p("\n【3】原样重跑：期望 0 次计算")
    rid, res = ex.run(user_id=USER, intent="原样重跑，验证缓存",
                      external_inputs={"fasta": FASTA})
    show_run(p, "重跑", rid, res)
    assert all(r.status == "reused" for r in res), "原样重跑应当全部命中缓存"
    p("  -> 0 次计算。缓存键 = 步骤版本 + 参数 + 输入内容哈希，与时间/路径无关。")

    # ---------- 4 ----------
    p("\n【4】换个文件名提交同一份内容：仍然命中")
    alias = SANDBOX / "test_copy.fasta"
    alias.write_bytes(FASTA.read_bytes())
    rid, res = ex.run(user_id=USER, intent="改名后重复提交",
                      external_inputs={"fasta": alias})
    show_run(p, "改名重交", rid, res)
    p("  -> 内容寻址的好处：文件名/路径/上传时间都不进缓存键，不会因重命名而白算一遍。")

    # ---------- 5 ----------
    p("\n【5】只改下游参数（round_digits 1 → 3）：前两步应命中")
    rid, res = ex.run(user_id=USER, intent="调整统计精度",
                      external_inputs={"fasta": FASTA},
                      overrides={"length_stats": {"round_digits": 3}})
    show_run(p, "改下游参数", rid, res)
    p("  -> 只有 length_stats 重算；step.params_json 记下了 round_digits=3，历史不会丢。")

    # ---------- 6 ----------
    p("\n【6】只改上游参数（不去 gap）：下游应全部重算")
    rid, res = ex.run(user_id=USER, intent="保留 gap 字符",
                      external_inputs={"fasta": FASTA},
                      overrides={"normalize_sequence": {"strip_gaps": False}})
    show_run(p, "改上游参数", rid, res)
    p("  -> read_fasta 命中，normalize + stats 重算。这就是「改一处、只重算受影响分支」。")

    # ---------- 7 ----------
    p("\n【7】把 stats 产物按策略降级为 meta_only（清理 payload）后再跑")
    last_stats = db.conn.execute(
        """SELECT a.* FROM step s JOIN step_io io ON io.step_id = s.id
           JOIN artifact a ON a.id = io.artifact_id
           WHERE s.run_id = ? AND s.name='length_stats' AND io.direction='output'""",
        (rid,),
    ).fetchone()
    assert last_stats is not None
    removed = store.delete(last_stats["object_path"])
    db.set_policy(int(last_stats["id"]), "meta_only", None)
    p(f"  已清理 artifact#{last_stats['id']} 的 payload（{kb(last_stats['size_bytes'])}），"
      f"元数据保留，object_path 置空")
    rid2, res2 = ex.run(user_id=USER, intent="产物清理后再跑（看缓存是否还成立）",
                        external_inputs={"fasta": FASTA},
                        overrides={"normalize_sequence": {"strip_gaps": False}})
    show_run(p, "清理后", rid2, res2)
    back = db.get_artifact(int(last_stats["id"]))
    p(f"  重算后 artifact#{back['id']}: object_path={back['object_path']}  "
      f"policy={back['save_policy']}  -> 内容写回来了，元数据行一直在，历史没断")
    p("  -> 缓存键本来命中，但产物已不在 → 判定为不可复用、自动重算。")
    p("     这解释了「保存策略」与「缓存是否有效」必须一起设计：省存储的代价是重新计算。")

    # ---------- 8 ----------
    p("\n【8】影响分析 / 复用收益 / 存储占用")
    norm = db.conn.execute(
        """SELECT a.* FROM step s JOIN step_io io ON io.step_id = s.id
           JOIN artifact a ON a.id = io.artifact_id
           WHERE s.run_id = ? AND s.name='normalize_sequence' AND io.direction='output'""",
        (rid,),
    ).fetchone()
    down = db.descendants(int(norm["id"]))
    p(f"  产物 artifact#{norm['id']}（normalized，{kb(norm['size_bytes'])}）的下游产物：")
    for aid in down:
        a = db.get_artifact(aid)
        p(f"    -> artifact#{a['id']:<3} kind={a['kind']:<14} {kb(a['size_bytes'])}  "
          f"policy={a['save_policy']}")
    p(f"  下游被影响步骤数：{len(db.consumers_of(int(norm['id'])))}")

    st = db.reuse_stats()
    total = st["steps"]
    p(f"\n  步骤记录 {total} 条：计算 {st['computed']} / 复用 {st['reused']}"
      f"（复用率 {st['reused'] / total:.0%}）")
    p(f"  累计计算耗时 {st['compute_ms']:.1f} ms，命中缓存省下约 {st['saved_ms']:.1f} ms")
    p("  （示例任务是毫秒级的玩具计算；换成 RFdiffusion / AlphaFold 这类真实模型后，")
    p("    省下的是分钟到小时级，这个倍率才是工作台要证明的收益）")
    p(f"  对象存储：{store.object_count()} 个对象 / {kb(store.total_bytes())}"
      f"；元数据库 {kb(db.disk_bytes())}")

    p("\n  最近执行历史（run 表）：")
    p(f"    {'run':<5}{'状态':<9}{'计算':<6}{'复用':<6}{'意图'}")
    for row in db.history(limit=8):
        p(f"    #{row['id']:<4}{row['status']:<9}{row['computed_count']:<6}"
          f"{row['reused_count']:<6}{row['intent']}")

    p("\n" + "=" * 78)
    p("结论：一条真实的小流程已经能记录来源、参数、版本、使用者，并按内容哈希跨执行复用；")
    p("      依赖关系由 step_io 推出，可做上游变更的影响分析；产物可按策略降级为仅元数据。")
    p("=" * 78)

    p.save(LOG)
    db.close()
    print(f"\n(日志已写入 {LOG})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
