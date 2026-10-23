"""SQLite 元数据库：schema + 最小 DAO。

表结构对应负责人给的元数据要求：
    工作流      -> workflow
    修改时间    -> run.started_at / step.created_at / artifact.created_at
    对应参数    -> step.params_json
    模型        -> step.task_version（工具/权重版本摘要）
    产物        -> artifact + step_io
    使用者 id   -> run.user_id
    使用策略    -> artifact.save_policy
    历史记录    -> step 只追加、不更新；同一 cache_key 多次命中可统计
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 工作流定义：同名流程的不同版本共存，历史结果才能解释得清
CREATE TABLE IF NOT EXISTS workflow (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    version     TEXT NOT NULL,
    description TEXT,
    code_digest TEXT,                  -- 步骤/依赖结构的哈希：结构变了就是新工作流版本
    created_at  REAL NOT NULL,
    UNIQUE (name, version)
);

-- 一次执行
CREATE TABLE IF NOT EXISTS run (
    id             INTEGER PRIMARY KEY,
    workflow_id    INTEGER NOT NULL REFERENCES workflow(id),
    user_id        TEXT NOT NULL,      -- 谁发起的
    intent         TEXT,               -- 这一次想干什么（人话，便于事后回溯）
    params_json    TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL,      -- running | success | failed
    started_at     REAL NOT NULL,
    finished_at    REAL,
    computed_count INTEGER NOT NULL DEFAULT 0,
    reused_count   INTEGER NOT NULL DEFAULT 0
);

-- 一次执行里的一步：append-only，命中也写一行（便于统计复用收益）
CREATE TABLE IF NOT EXISTS step (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES run(id),
    name         TEXT NOT NULL,
    task_version TEXT NOT NULL,        -- 代码/模型版本（真实项目里放权重摘要）
    params_json  TEXT NOT NULL DEFAULT '{}',
    cache_key    TEXT NOT NULL,        -- sha256(step, version, params, 输入内容哈希)
    status       TEXT NOT NULL,        -- computed | reused | failed
    reused_from  INTEGER REFERENCES step(id),
    created_at   REAL NOT NULL,
    duration_ms  REAL,
    error        TEXT
);

-- 产物：内容寻址，同一份内容只存一份
CREATE TABLE IF NOT EXISTS artifact (
    id           INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL,        -- fasta | sequence_set | stats | ...
    media_type   TEXT,
    size_bytes   INTEGER,
    object_path  TEXT,                 -- 相对 store 根目录；NULL = 只留元数据，payload 已清理
    save_policy  TEXT NOT NULL,        -- keep | cache | meta_only
    created_at   REAL NOT NULL,
    last_used_at REAL,
    use_count    INTEGER NOT NULL DEFAULT 0
);

-- 步骤与产物的连线；依赖关系由这张表推出，不靠工具名硬拼
CREATE TABLE IF NOT EXISTS step_io (
    step_id     INTEGER NOT NULL REFERENCES step(id),
    direction   TEXT NOT NULL,         -- input | output
    port        TEXT NOT NULL,
    artifact_id INTEGER NOT NULL REFERENCES artifact(id),
    PRIMARY KEY (step_id, direction, port)
);

CREATE INDEX IF NOT EXISTS idx_step_cache    ON step (cache_key, status);
CREATE INDEX IF NOT EXISTS idx_step_run      ON step (run_id);
CREATE INDEX IF NOT EXISTS idx_io_artifact   ON step_io (artifact_id);
CREATE INDEX IF NOT EXISTS idx_artifact_kind ON artifact (kind);
"""


def now() -> float:
    return time.time()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class MetaDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")   # 读写不互斥
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript(DDL)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        # WAL 模式下新写入的页暂存在 meta.sqlite-wal 里，主库文件可能只有几 KB。
        # 退出前 checkpoint 把它并回主库并清空 -wal，否则"只拷 meta.sqlite 就能带走数据"
        # 这句话不成立（会丢掉最近的写入）。
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        self.conn.close()

    def disk_bytes(self) -> int:
        """元数据落盘后的实际占用字节数。

        WAL 模式下有两个失真方向，都必须先 checkpoint 才能量准：
          只量主库文件 -> 低估（新数据还在 -wal 里，本库实测 4 KB vs 60 KB）
          主库 + -wal  -> 高估（-wal 不解压地累积整个会话的写页，本库实测到 700 KB）
        checkpoint 把 -wal 并回主库并截断，此时主库文件就是真实体积。
        """
        try:
            self.conn.commit()
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        total = 0
        for suffix in ("", "-wal"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                total += p.stat().st_size
        return total

    # ---------------- workflow ----------------
    def upsert_workflow(self, name: str, version: str, description: str, code_digest: str) -> int:
        cur = self.conn.execute("SELECT id FROM workflow WHERE name = ? AND version = ?", (name, version))
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO workflow(name, version, description, code_digest, created_at) VALUES (?,?,?,?,?)",
            (name, version, description, code_digest, now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # ---------------- run ----------------
    def create_run(self, workflow_id: int, user_id: str, intent: str, params: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO run(workflow_id, user_id, intent, params_json, status, started_at) VALUES (?,?,?,?,?,?)",
            (workflow_id, user_id, intent, dumps(params), "running", now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, computed: int, reused: int) -> None:
        self.conn.execute(
            "UPDATE run SET status=?, finished_at=?, computed_count=?, reused_count=? WHERE id=?",
            (status, now(), computed, reused, run_id),
        )
        self.conn.commit()

    # ---------------- artifact ----------------
    def upsert_artifact(
        self,
        content_hash: str,
        kind: str,
        media_type: str | None,
        size: int,
        object_path: str | None,
        save_policy: str,
    ) -> int:
        row = self.conn.execute(
            "SELECT id, object_path FROM artifact WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if row:
            if row["object_path"] is None and object_path is not None:
                # 之前按策略清理过 payload，这次重算又写回来了：恢复可用状态
                self.conn.execute(
                    "UPDATE artifact SET object_path=?, save_policy=?, last_used_at=?,"
                    " use_count=use_count+1 WHERE id=?",
                    (object_path, save_policy, now(), row["id"]),
                )
            else:
                self.conn.execute(
                    "UPDATE artifact SET last_used_at=?, use_count=use_count+1 WHERE id=?",
                    (now(), row["id"]),
                )
            return int(row["id"])
        cur = self.conn.execute(
            """INSERT INTO artifact(content_hash, kind, media_type, size_bytes, object_path,
                                    save_policy, created_at, last_used_at, use_count)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            (content_hash, kind, media_type, size, object_path, save_policy, now(), now()),
        )
        return int(cur.lastrowid)

    def get_artifact(self, artifact_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM artifact WHERE id=?", (artifact_id,)).fetchone()

    def set_policy(self, artifact_id: int, policy: str, object_path: str | None) -> None:
        """清理 payload，但保留元数据（可追溯"曾经存在过什么"）。"""
        self.conn.execute(
            "UPDATE artifact SET save_policy=?, object_path=? WHERE id=?",
            (policy, object_path, artifact_id),
        )
        self.conn.commit()

    # ---------------- step ----------------
    def add_step(
        self,
        run_id: int,
        name: str,
        task_version: str,
        params: dict,
        cache_key: str,
        status: str,
        reused_from: int | None,
        duration_ms: float | None,
        error: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO step(run_id, name, task_version, params_json, cache_key, status,
                                reused_from, created_at, duration_ms, error)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (run_id, name, task_version, dumps(params), cache_key, status,
             reused_from, now(), duration_ms, error),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def find_reusable_step(self, cache_key: str) -> sqlite3.Row | None:
        """按 cache_key 找最近一次成功算出的步骤（跨 run 复用）。"""
        return self.conn.execute(
            """SELECT * FROM step
               WHERE cache_key = ? AND status IN ('computed','reused') AND error IS NULL
               ORDER BY id DESC LIMIT 1""",
            (cache_key,),
        ).fetchone()

    def link(self, step_id: int, direction: str, port: str, artifact_id: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO step_io(step_id, direction, port, artifact_id) VALUES (?,?,?,?)",
            (step_id, direction, port, artifact_id),
        )

    def outputs_of_step(self, step_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT io.port, a.* FROM step_io io JOIN artifact a ON a.id = io.artifact_id
               WHERE io.step_id = ? AND io.direction = 'output' ORDER BY io.port""",
            (step_id,),
        ).fetchall()

    # ---------------- 依赖 / 血缘 ----------------
    def producers_of(self, artifact_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT s.* FROM step_io io JOIN step s ON s.id = io.step_id
               WHERE io.artifact_id = ? AND io.direction = 'output'""",
            (artifact_id,),
        ).fetchall()

    def consumers_of(self, artifact_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT s.*, io.port FROM step_io io JOIN step s ON s.id = io.step_id
               WHERE io.artifact_id = ? AND io.direction = 'input' ORDER BY s.id""",
            (artifact_id,),
        ).fetchall()

    def descendants(self, artifact_id: int) -> list[int]:
        """影响分析：这个产物变了，下游哪些产物会受影响（BFS）。"""
        seen: set[int] = set()
        frontier = [artifact_id]
        while frontier:
            aid = frontier.pop()
            for row in self.consumers_of(aid):
                for out in self.outputs_of_step(int(row["id"])):
                    if out["id"] not in seen:
                        seen.add(int(out["id"]))
                        frontier.append(int(out["id"]))
        return sorted(seen)

    # ---------------- 报表 ----------------
    def history(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT r.id, r.user_id, r.intent, r.status, r.started_at,
                      r.computed_count, r.reused_count, w.name AS workflow
               FROM run r JOIN workflow w ON w.id = r.workflow_id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def run_steps(self, run_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM step WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()

    def reuse_stats(self) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT
                 COUNT(*) AS steps,
                 SUM(CASE WHEN status='computed' THEN 1 ELSE 0 END) AS computed,
                 SUM(CASE WHEN status='reused'   THEN 1 ELSE 0 END) AS reused,
                 COALESCE(SUM(CASE WHEN status='computed' THEN duration_ms ELSE 0 END), 0) AS compute_ms
               FROM step"""
        ).fetchone()
        # 复用是链式传递的：#20 → #17 → #10 → #1，其中 #17、#10 本身也是 reused，
        # duration_ms 记 0。只查一跳会把它们的 0 累加进来，严重低估收益
        # （本库实测只查一跳 0.24 ms，回溯到底 0.62 ms）。必须沿 reused_from
        # 一路回溯到真正算过的那条 computed 记录，取它的耗时。
        nodes = {
            int(r["id"]): (r["status"], r["reused_from"], r["duration_ms"])
            for r in self.conn.execute(
                "SELECT id, status, reused_from, duration_ms FROM step"
            )
        }
        saved = 0.0
        for status, origin, _ in nodes.values():
            if status != "reused" or origin is None:
                continue
            cur, hops = int(origin), 0
            while hops < 64:  # 防御成环，正常链长远小于此
                node = nodes.get(cur)
                if node is None:
                    break
                st, nxt, dur = node
                if st == "computed":
                    saved += dur or 0.0
                    break
                if st != "reused" or nxt is None:
                    break
                cur, hops = int(nxt), hops + 1
        return {
            "steps": row["steps"] or 0,
            "computed": row["computed"] or 0,
            "reused": row["reused"] or 0,
            "compute_ms": row["compute_ms"] or 0.0,
            "saved_ms": saved or 0.0,
        }

    def table_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name in ("workflow", "run", "step", "artifact", "step_io"):
            out[name] = int(self.conn.execute(f"SELECT COUNT(*) c FROM {name}").fetchone()["c"])
        return out

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")
