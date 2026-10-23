"""内容寻址对象存储（Content-Addressed Storage）。

- 所有 payload（FASTA、规范化序列、统计 JSON……）都按 sha256 落盘，路径 = objects/<前2位>/<完整哈希>
- 同一份内容只存一份；元数据里只放 content_hash + object_path
- 与元数据库解耦：SQLite 只存"谁、什么时候、用什么参数产生了什么哈希"，
  换 PostgreSQL / 换云对象存储时，这一层不需要改调用方
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


class ObjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)

    # ---------- 基础 ----------
    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _path_of(self, digest: str) -> Path:
        return self.root / "objects" / digest[:2] / digest

    def relpath(self, digest: str) -> str:
        return str(self._path_of(digest).relative_to(self.root)).replace("\\", "/")

    # ---------- 写 ----------
    def put(self, data: bytes) -> tuple[str, str, int]:
        """写入内容，返回 (content_hash, object_path, size)。已存在则直接复用。"""
        digest = self.hash_bytes(data)
        path = self._path_of(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + f".tmp{os.getpid()}")
            tmp.write_bytes(data)
            os.replace(tmp, path)  # 原子替换，避免半截文件
        return digest, self.relpath(digest), len(data)

    # ---------- 读 ----------
    def exists(self, relpath: str | None) -> bool:
        return bool(relpath) and (self.root / relpath).exists()

    def get(self, relpath: str) -> bytes:
        return (self.root / relpath).read_bytes()

    def delete(self, relpath: str) -> bool:
        """按保存策略清理 payload（元数据行保留，object_path 置空）。"""
        p = self.root / relpath
        if p.exists():
            p.unlink()
            return True
        return False

    # ---------- 统计 ----------
    def total_bytes(self) -> int:
        total = 0
        for p in (self.root / "objects").rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def object_count(self) -> int:
        return sum(1 for p in (self.root / "objects").rglob("*") if p.is_file())

    def reset(self) -> None:
        shutil.rmtree(self.root / "objects", ignore_errors=True)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)
