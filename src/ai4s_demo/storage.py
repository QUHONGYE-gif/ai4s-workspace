"""One atomic JSON envelope per workflow, protected within a single process."""

import json
import os
import re
import tempfile
import threading
from pathlib import Path


class Problem(Exception):
    def __init__(self, status, message, *, details=None):
        self.status, self.message, self.details = status, message, details
        super().__init__(message)


def identifier(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise Problem(400, "无效的资源标识")
    return value


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def path(self, kind, resource_id):
        return self.root / kind / f"{identifier(resource_id)}.json"

    def read(self, kind, resource_id, *, include_deleted=False):
        try:
            value = json.loads(self.path(kind, resource_id).read_text())
            if value.get("deleted") and not include_deleted:
                raise Problem(404, "该记录已删除，可从回收站恢复")
            return value
        except FileNotFoundError:
            raise Problem(404, "没有找到该资源") from None

    def write(self, kind, resource_id, value):
        path = self.path(kind, resource_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def set_deleted(self, kind, resource_id, expected_revision, deleted):
        # Retain the envelope and invalidate all proposals made before deletion.
        with self.lock:
            value = self.read(kind, resource_id, include_deleted=True)
            revision_holder = value["draft"] if kind == "workflows" else value
            if revision_holder["revision"] != expected_revision:
                raise Problem(409, "记录已变化，请刷新列表后重试")
            if bool(value.get("deleted")) != deleted:
                value["deleted"] = deleted
                revision_holder["revision"] += 1
                self.write(kind, resource_id, value)
            return {"id": resource_id, "revision": revision_holder["revision"], "deleted": deleted}

    def list_workflows(self, *, deleted=False):
        with self.lock:
            return [{"id": d["draft"]["id"], "name": d["draft"]["name"], "revision": d["draft"]["revision"]}
                    for p in sorted((self.root / "workflows").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if bool((d := json.loads(p.read_text())).get("deleted")) == deleted]
