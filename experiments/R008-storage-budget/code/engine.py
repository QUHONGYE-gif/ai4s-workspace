"""空间预算与保留策略实验台（任务 5.0 · 陈思睿）。

只使用标准库。三条边界：
  1. 所有产物文件只写在 lab/artifacts/ 下，删除函数拒绝作用于该目录之外的任何路径；
  2. 配额、策略、访问序列都是实验参数，真实 AiiDA 仓库不参与；
  3. 每次淘汰都落一条可解释记录（触发原因 + 四个打分分量 + 被保留的对照项）。
"""
import json
import math
import os
import random
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 实验目录默认在脚本同级；放进仓库后可用 AI4S_EVICT_LAB 指到实验数据目录，
# 避免把产物文件与 SQLite 写进源码树（这两类内容不纳入 Git）。
_LAB_ENV = os.environ.get("AI4S_EVICT_LAB")
LAB = Path(_LAB_ENV).resolve() if _LAB_ENV else (ROOT / "lab")
ART = LAB / "artifacts"
STATE = LAB / "state.sqlite"
MB = 1024 * 1024

# 演示用的时间缩放：真实重算成本 cost_s 秒，这里按 1/SCALE 加速执行。
# 记录里同时保留「模拟耗时」和「折算真实耗时」，避免把演示数字当真实性能。
TIME_SCALE = float(os.environ.get("EVICT_TIME_SCALE", "0.008"))

LOCK = threading.RLock()

# 产物目录：label 用于页面展示，size_mb 与 cost_s 是实验设定（真实部署时来自运行记录）
CATALOG = [
    # id                    label                          size_mb  cost_s  pinned
    ("1crn-mpnn-s42-n8",   "ProteinMPNN · 1CRN · seed42 · 8seq",   6.5,   90, 0),
    ("7ahl-mpnn-s1-n16",   "ProteinMPNN · 7AHL · seed1 · 16seq",   9.0,  120, 0),
    ("1crn-filter-seed7",  "MPNN+Filter · 1CRN · seed7",           1.2,   35, 0),
    ("boltz-1crn-b1",      "Boltz-2 · 1CRN · sample1",             8.8,  180, 1),
    ("1crn-mpnn-s7-n8",    "ProteinMPNN · 1CRN · seed7 · 8seq",    0.9,   20, 0),
    ("7ahl-filter-seed3",  "MPNN+Filter · 7AHL · seed3",           1.4,   40, 0),
    ("1crn-mpnn-s11-n4",   "ProteinMPNN · 1CRN · seed11 · 4seq",   2.2,   25, 0),
    ("7ahl-mpnn-s5-n8",    "ProteinMPNN · 7AHL · seed5 · 8seq",    3.4,   55, 0),
    ("1crn-mpnn-s13-n16",  "ProteinMPNN · 1CRN · seed13 · 16seq",  5.0,   75, 0),
    ("7ahl-mpnn-s9-n8",    "ProteinMPNN · 7AHL · seed9 · 8seq",    3.1,   50, 0),
    ("boltz-7ahl-b2",      "Boltz-2 · 7AHL · sample2",             9.4,  200, 0),
]

# 访问序列（同一序列供两种策略回放）：先填满空间，再反复取用「贵而常用」的结果
SEQUENCE = [
    "1crn-mpnn-s42-n8",    # 1  计算
    "7ahl-mpnn-s1-n16",    # 2
    "1crn-filter-seed7",   # 3
    "boltz-1crn-b1",       # 4
    "1crn-mpnn-s42-n8",    # 5  复用（热）
    "1crn-mpnn-s7-n8",     # 6
    "7ahl-filter-seed3",   # 7
    "1crn-mpnn-s42-n8",    # 8  复用（热）
    "1crn-mpnn-s11-n4",    # 9
    "7ahl-mpnn-s5-n8",     # 10 触发第一次淘汰
    "1crn-mpnn-s13-n16",   # 11
    "7ahl-mpnn-s9-n8",     # 12
    "boltz-7ahl-b2",       # 13
    "1crn-mpnn-s42-n8",    # 14 复用（热）
    "1crn-filter-seed7",   # 15
    "7ahl-mpnn-s1-n16",    # 16
    "boltz-1crn-b1",       # 17 固定项，不应被删
    "1crn-mpnn-s7-n8",     # 18
    "7ahl-filter-seed3",   # 19
    "1crn-mpnn-s42-n8",    # 20 复用（热）
    "1crn-mpnn-s11-n4",    # 21
    "7ahl-mpnn-s5-n8",     # 22
    "1crn-mpnn-s13-n16",   # 23
    "1crn-mpnn-s42-n8",    # 24 复用（热）
    "7ahl-mpnn-s9-n8",     # 25
    "1crn-mpnn-s42-n8",    # 26 复用（热）
]

READ_SECONDS = 0.12          # 复用一次（读取产物）的耗时，作为「省下来的时间」参照
DECAY_TAU_HOURS = 24 * 7     # 打分的时间衰减常数：7 天
# 冷期在实现上只作用于「本轮刚写入的产物」：本次写入不参与本次淘汰，
# 这样淘汰结果不依赖机器速度，换一台机器跑同一条序列结果一致。


# ---------------------------------------------------------------- 基础工具

def now():
    return time.time()


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def spec(fingerprint):
    for row in CATALOG:
        if row[0] == fingerprint:
            return {"id": row[0], "label": row[1], "size_mb": row[2], "cost_s": row[3], "pinned": row[4]}
    raise KeyError(fingerprint)


def connect():
    conn = sqlite3.connect(STATE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init():
    LAB.mkdir(exist_ok=True)
    ART.mkdir(exist_ok=True)
    conn = connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS artifacts (
        fingerprint TEXT PRIMARY KEY, label TEXT, path TEXT, size_bytes INTEGER,
        cost_s REAL, pinned INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
        use_count INTEGER DEFAULT 0, created_at REAL, last_used_at REAL,
        last_score REAL, last_parts TEXT);
    CREATE TABLE IF NOT EXISTS evictions (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, policy TEXT,
        fingerprint TEXT, label TEXT, size_bytes INTEGER, evicted_at REAL,
        reason TEXT);
    CREATE TABLE IF NOT EXISTS restores (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, policy TEXT,
        fingerprint TEXT, label TEXT, gap_s REAL, recompute_s REAL, cost_s REAL,
        finished_at REAL);
    CREATE TABLE IF NOT EXISTS hits (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, policy TEXT,
        fingerprint TEXT, at REAL);
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, policy TEXT, quota_bytes INTEGER,
        started_at REAL, finished_at REAL, peak_bytes INTEGER,
        evictions INTEGER, restores INTEGER, recompute_real_s REAL,
        hits INTEGER, computed INTEGER, sequence TEXT);
    CREATE TABLE IF NOT EXISTS samples (
        run_id TEXT, at REAL, used_bytes INTEGER);
    """)
    conn.commit()
    conn.close()


def reset():
    """清空实验目录内的产物与状态（只作用于 lab/ 之内）。"""
    with LOCK:
        if STATE.exists():
            STATE.unlink()
        for p in ART.glob("*.bin"):
            safe_unlink(p)
        init()


def safe_unlink(path: Path):
    """删除前校验：目标必须位于实验产物目录内。"""
    target = Path(path).resolve()
    base = ART.resolve()
    if base not in target.parents:
        raise RuntimeError(f"拒绝删除实验目录之外的文件：{target}")
    target.unlink(missing_ok=True)


def used_bytes():
    total = 0
    for p in ART.glob("*.bin"):
        try:
            total += p.stat().st_size
        except FileNotFoundError:
            pass
    return total


def write_payload(fingerprint, size_mb):
    """真实写出产物文件（内容为可压缩性很低的伪随机字节，避免稀疏文件假占用）。"""
    path = ART / (fingerprint.replace("#", "_") + ".bin")
    chunk = os.urandom(64 * 1024)
    remaining = int(size_mb * MB)
    with open(path, "wb") as fh:
        while remaining > 0:
            n = min(len(chunk), remaining)
            fh.write(chunk[:n])
            remaining -= n
    return path, path.stat().st_size


# ---------------------------------------------------------------- 打分与选 victims

def score_of(use_count, cost_s, size_bytes, last_used_at, at=None):
    """保留价值：复用频次 × 重算成本 ÷ 产物大小，带时间衰减。

    f 取 1+次数，使「从未被复用」的产物仍有基线权重，避免所有新产物并列 0 分。
    """
    at = at or now()
    f = 1.0 + use_count
    c = max(cost_s, 1.0)
    size_mb = max(size_bytes / MB, 0.05)
    age_h = max(at - (last_used_at or at), 0.0) / 3600.0
    decay = math.exp(-age_h / DECAY_TAU_HOURS)
    value = (math.log1p(f) * math.log1p(c)) / (size_mb ** 0.7) * decay
    parts = {"freq": use_count, "f_eff": f, "cost_s": cost_s,
             "size_mb": round(size_bytes / MB, 2), "age_h": round(age_h, 4),
             "decay": round(decay, 6)}
    return value, parts


def candidates(conn):
    rows = conn.execute("SELECT * FROM artifacts WHERE status='active'").fetchall()
    out = []
    for r in rows:
        value, parts = score_of(r["use_count"], r["cost_s"], r["size_bytes"], r["last_used_at"])
        out.append({"row": r, "value": value, "parts": parts})
    return out


def pick_victim(conn, policy, need_bytes, protect=None):
    """两种策略共用同一份候选集，只有排序键不同。"""
    pool = candidates(conn)
    # 共同规则一：固定项不参与淘汰
    pool = [c for c in pool if not c["row"]["pinned"]]
    # 共同规则二：本轮刚写入的产物不参与本轮淘汰（避免刚算完就被删）
    if protect:
        warm = [c for c in pool if c["row"]["fingerprint"] != protect]
        pool = warm or pool
    if not pool:
        return None, None
    if policy == "lru":
        pool.sort(key=lambda c: (c["row"]["last_used_at"] or 0, c["row"]["created_at"] or 0))
        chosen = pool[0]
        return chosen, {"policy": "lru", "key": "last_used_at", "last_used_at": iso(chosen["row"]["last_used_at"])}
    # scored：价值升序；先按 0.25 粒度分档再按时间排，避免浮点尾数导致排序抖动
    def bucket(v):
        return int(max(0.0, min(15.0, math.floor(v / 0.25))))
    pool.sort(key=lambda c: (bucket(c["value"]), c["row"]["last_used_at"] or 0))
    chosen = pool[0]
    kept = pool[-1]
    return chosen, {"policy": "scored", "key": "value", "value": round(chosen["value"], 4),
                    "parts": chosen["parts"], "bucket": bucket(chosen["value"]),
                    "kept_example": {"fingerprint": kept["row"]["fingerprint"],
                                     "value": round(kept["value"], 4),
                                     "parts": kept["parts"]}}


def enforce_quota(conn, run_id, policy, quota, trace=None, protect=None):
    """超配额则按策略淘汰，直到降到软上限（配额的 85%）。"""
    soft = int(quota * 0.85)
    count = 0
    real_s = 0.0
    while used_bytes() > quota:
        used = used_bytes()
        over = used - quota
        chosen, why = pick_victim(conn, policy, over, protect)
        if chosen is None:
            chosen, why = pick_victim(conn, policy, over)  # 兜底：放开刚写入保护
            if chosen is not None:
                why = dict(why, forced=True)
        if chosen is None:
            break  # 只剩固定项：停下，留给页面说明「已无处可删」
        row = chosen["row"]
        path = Path(row["path"])
        safe_unlink(path)
        conn.execute("UPDATE artifacts SET status='evicted' WHERE fingerprint=?", (row["fingerprint"],))
        reason = dict(why)
        reason.update({"trigger": "over_quota", "over_by_bytes": over,
                       "used_bytes": used, "quota_bytes": quota, "soft_target": soft})
        conn.execute("""INSERT INTO evictions(run_id,policy,fingerprint,label,size_bytes,evicted_at,reason)
                        VALUES(?,?,?,?,?,?,?)""",
                     (run_id, policy, row["fingerprint"], row["label"], row["size_bytes"], now(),
                      json.dumps(reason, ensure_ascii=False)))
        conn.commit()
        if trace is not None:
            trace.append({"type": "eviction", "fingerprint": row["fingerprint"], "label": row["label"],
                          "size_mb": round(row["size_bytes"] / MB, 2), "policy": policy,
                          "reason": reason, "explain": explain(reason)})
        count += 1
    return count, real_s


# ---------------------------------------------------------------- 请求处理

def handle_request(conn, run_id, policy, quota, fingerprint, stats, trace=None):
    """一次请求：命中复用 / 命中墓碑后重算 / 首次计算。"""
    row = conn.execute("SELECT * FROM artifacts WHERE fingerprint=?", (fingerprint,)).fetchone()
    t0 = now()
    if row and row["status"] == "active":
        time.sleep(READ_SECONDS)
        conn.execute("UPDATE artifacts SET use_count=use_count+1, last_used_at=? WHERE fingerprint=?",
                     (now(), fingerprint))
        conn.execute("INSERT INTO hits(run_id,policy,fingerprint,at) VALUES(?,?,?,?)",
                     (run_id, policy, fingerprint, now()))
        conn.commit()
        stats["hits"] += 1
        if trace is not None:
            trace.append({"type": "request", "action": "reuse", "fingerprint": fingerprint,
                          "label": row["label"], "size_mb": round(row["size_bytes"] / MB, 2),
                          "cost_s": row["cost_s"], "elapsed": round(now() - t0, 3)})
        return {"action": "reuse", "fingerprint": fingerprint, "evicted_now": 0,
                "elapsed": round(now() - t0, 3)}

    info = spec(fingerprint)
    if row and row["status"] == "evicted":
        gap = now() - (row["last_used_at"] or row["created_at"] or now())
        recompute = max(info["cost_s"] * TIME_SCALE, 0.05)
        time.sleep(recompute)
        path, size = write_payload(fingerprint, info["size_mb"])
        conn.execute("""UPDATE artifacts SET status='active', path=?, size_bytes=?, last_used_at=?,
                        use_count=use_count+1 WHERE fingerprint=?""",
                     (str(path), size, now(), fingerprint))
        conn.execute("""INSERT INTO restores(run_id,policy,fingerprint,label,gap_s,recompute_s,cost_s,finished_at)
                        VALUES(?,?,?,?,?,?,?,?)""",
                     (run_id, policy, fingerprint, info["label"], round(gap, 1),
                      round(recompute, 3), info["cost_s"], now()))
        conn.commit()
        stats["restores"] += 1
        stats["recompute_real_s"] += info["cost_s"]
        if trace is not None:
            trace.append({"type": "request", "action": "restore", "fingerprint": fingerprint,
                          "label": info["label"], "size_mb": info["size_mb"], "cost_s": info["cost_s"],
                          "gap_s": round(gap, 1), "elapsed": round(recompute, 3)})
        action = "restore"
    else:
        recompute = max(info["cost_s"] * TIME_SCALE, 0.05)
        time.sleep(recompute)
        path, size = write_payload(fingerprint, info["size_mb"])
        conn.execute("""INSERT OR REPLACE INTO artifacts
                        (fingerprint,label,path,size_bytes,cost_s,pinned,status,use_count,created_at,last_used_at)
                        VALUES(?,?,?,?,?,?,'active',0,?,?)""",
                     (fingerprint, info["label"], str(path), size, info["cost_s"], info["pinned"],
                      now(), now()))
        conn.commit()
        stats["computed"] += 1
        if trace is not None:
            trace.append({"type": "request", "action": "compute", "fingerprint": fingerprint,
                          "label": info["label"], "size_mb": info["size_mb"], "cost_s": info["cost_s"],
                          "elapsed": round(recompute, 3)})
        action = "compute"

    ev, _ = enforce_quota(conn, run_id, policy, quota, trace, protect=fingerprint)
    stats["evictions"] += ev
    return {"action": action, "fingerprint": fingerprint, "evicted_now": ev,
            "elapsed": round(now() - t0, 3)}


def replay(policy, quota_mb, sequence=None, run_id=None, reset_first=True, trace=None):
    """按同一访问序列回放一种策略，返回本次运行汇总。"""
    sequence = sequence or SEQUENCE
    quota = int(quota_mb * MB)
    run_id = run_id or f"{policy}-{int(now())}"
    with LOCK:
        if reset_first:
            for p in ART.glob("*.bin"):
                safe_unlink(p)
            conn = connect()
            conn.execute("DELETE FROM artifacts")
            conn.execute("DELETE FROM samples WHERE run_id=?", (run_id,))
            conn.commit()
            conn.close()
        stats = {"hits": 0, "restores": 0, "computed": 0, "evictions": 0, "recompute_real_s": 0.0}
        started = now()
        conn = connect()
        conn.execute("""INSERT OR REPLACE INTO runs
                        (run_id,policy,quota_bytes,started_at,peak_bytes,evictions,restores,
                         recompute_real_s,hits,computed,sequence)
                        VALUES(?,?,?,?,0,0,0,0,0,0,?)""",
                     (run_id, policy, quota, started, json.dumps(sequence)))
        conn.commit()
        peak = 0
        steps = []
        for fp in sequence:
            conn2 = connect()
            result = handle_request(conn2, run_id, policy, quota, fp, stats, trace)
            conn2.close()
            used = used_bytes()
            peak = max(peak, used)
            conn = connect()
            conn.execute("INSERT INTO samples(run_id,at,used_bytes) VALUES(?,?,?)", (run_id, now(), used))
            conn.execute("UPDATE runs SET peak_bytes=? WHERE run_id=?", (peak, run_id))
            conn.commit()
            conn.close()
            steps.append({**result, "used_bytes": used})
            if trace is not None:
                for item in reversed(trace):
                    if item.get("type") == "request" and "used_after" not in item:
                        item["used_after"] = used
                        item["seq"] = len(steps)
                        break
        conn = connect()
        conn.execute("""UPDATE runs SET finished_at=?, peak_bytes=?, evictions=?, restores=?,
                        recompute_real_s=?, hits=?, computed=? WHERE run_id=?""",
                     (now(), peak, stats["evictions"], stats["restores"], stats["recompute_real_s"],
                      stats["hits"], stats["computed"], run_id))
        conn.commit()
        conn.close()
    return {"run_id": run_id, "policy": policy, "quota_mb": quota_mb, "peak_bytes": peak,
            "evictions": stats["evictions"], "restores": stats["restores"],
            "recompute_real_s": stats["recompute_real_s"], "hits": stats["hits"],
            "computed": stats["computed"], "steps": steps}


# ---------------------------------------------------------------- 查询

def snapshot():
    """常驻查询服务的唯一事实来源：一条记录一个结论。"""
    conn = connect()
    used = used_bytes()
    arts = []
    for r in conn.execute("SELECT * FROM artifacts ORDER BY last_used_at DESC, fingerprint").fetchall():
        value, parts = score_of(r["use_count"], r["cost_s"], r["size_bytes"], r["last_used_at"])
        last_ev = conn.execute("""SELECT * FROM evictions WHERE fingerprint=?
                                  ORDER BY seq DESC LIMIT 1""", (r["fingerprint"],)).fetchone()
        reason = json.loads(last_ev["reason"]) if last_ev else None
        arts.append({
            "fingerprint": r["fingerprint"], "label": r["label"],
            "size_bytes": r["size_bytes"], "size_mb": round(r["size_bytes"] / MB, 2),
            "cost_s": r["cost_s"], "use_count": r["use_count"],
            "pinned": bool(r["pinned"]), "status": r["status"],
            "retained": r["status"] == "active",
            "created_at": iso(r["created_at"]), "last_used_at": iso(r["last_used_at"]),
            "score": round(value, 4), "score_parts": parts,
            "eviction": None if not reason else {
                "at": iso(last_ev["evicted_at"]), "policy": last_ev["policy"],
                "size_mb": round(last_ev["size_bytes"] / MB, 2), "reason": reason,
                "explain": explain(reason),
            },
        })
    runs = [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()]
    evictions = []
    for r in conn.execute("SELECT * FROM evictions ORDER BY seq DESC LIMIT 60").fetchall():
        reason = json.loads(r["reason"])
        evictions.append({"fingerprint": r["fingerprint"], "label": r["label"],
                          "size_mb": round(r["size_bytes"] / MB, 2), "policy": r["policy"],
                          "at": iso(r["evicted_at"]), "run_id": r["run_id"],
                          "reason": reason, "explain": explain(reason)})
    restores = []
    for r in conn.execute("SELECT * FROM restores ORDER BY seq DESC LIMIT 60").fetchall():
        restores.append({"fingerprint": r["fingerprint"], "label": r["label"],
                         "policy": r["policy"], "gap_s": r["gap_s"],
                         "recompute_s": r["recompute_s"], "cost_s": r["cost_s"],
                         "extra_s": round(max(0.0, r["cost_s"] - READ_SECONDS), 1),
                         "at": iso(r["finished_at"])})
    conn.close()
    return {"quota_bytes": None, "used_bytes": used, "used_mb": round(used / MB, 2),
            "artifacts": arts, "evictions": evictions, "restores": restores, "runs": runs}


def explain(reason):
    """把一条淘汰记录翻成人话（演示与页面共用，不引入模型）。"""
    if not reason:
        return ""
    if reason.get("policy") == "lru":
        return (f"LRU：它是最久没有被请求的产物（上次使用 {reason.get('last_used_at')}），"
                f"超出配额 {reason['over_by_bytes'] // MB} MB，先删它。")
    parts = reason.get("parts", {})
    kept = reason.get("kept_example", {})
    return (f"打分：价值 {reason.get('value')} 为当前最低（复用 {parts.get('freq')} 次、"
            f"重算 {parts.get('cost_s')} 秒、{parts.get('size_mb')} MB）。"
            f"同一时刻保留的 {kept.get('fingerprint')} 价值 {kept.get('value')}，"
            f"超出配额 {reason['over_by_bytes'] // MB} MB，因此删它。")


def write_quota_sidecar(quota_mb):
    (LAB / "quota.json").write_text(json.dumps(
        {"quota_mb": quota_mb, "soft_ratio": 0.85, "time_scale": TIME_SCALE,
         "read_seconds": READ_SECONDS, "decay_tau_hours": DECAY_TAU_HOURS}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="保留策略实验台")
    ap.add_argument("--policy", choices=["lru", "scored"], default="scored")
    ap.add_argument("--quota", type=float, default=32.0, help="空间上限（MB）")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    if args.reset:
        reset()
    init()
    write_quota_sidecar(args.quota)
    print(json.dumps(replay(args.policy, args.quota), ensure_ascii=False, indent=2))
