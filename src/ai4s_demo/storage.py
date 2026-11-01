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

    def read(self, kind, resource_id):
        try:
            return json.loads(self.path(kind, resource_id).read_text())
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

    def list_workflows(self):
        with self.lock:
            return [{"id": d["draft"]["id"], "name": d["draft"]["name"], "revision": d["draft"]["revision"]}
                    for p in sorted((self.root / "workflows").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if (d := json.loads(p.read_text()))]
