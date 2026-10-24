"""Atomic, revisioned snapshots separated by an opaque browser namespace."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock


class ConflictError(Exception):
    """A different tab has saved a newer revision."""


def validate_state(state):
    """Validate the persisted demo contract, not scientific correctness."""
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("Unsupported demo state version")
    for name in ("catalog", "experiments"):
        if not isinstance(state.get(name), list):
            raise ValueError(f"{name} must be an array")
    if len(state["catalog"]) > 3000 or len(state["experiments"]) > 1000:
        raise ValueError("Demo state exceeds record limits")
    if not isinstance(state.get("drafts"), dict):
        raise ValueError("drafts must be an object")
    if type(state.get("next")) is not int or state["next"] < 1:
        raise ValueError("next must be a positive integer")
    for name in ("catalog", "experiments"):
        ids = [
            item.get("id") if isinstance(item, dict) else None for item in state[name]
        ]
        if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{name} has invalid or duplicate IDs")
    # Keep the existing browser import/export schema. The backend never executes it.
    return state


class SnapshotStore:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = RLock()

    def _path(self, session):
        if not isinstance(session, str) or not re.fullmatch(r"[a-f0-9]{32}", session):
            raise ValueError("A valid X-Demo-Session header is required")
        return self.directory / f"{session}.json"

    def load(self, session):
        with self.lock:
            path = self._path(session)
            if not path.exists():
                return {"revision": 0, "state": None}
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session, expected_revision, state):
        validate_state(state)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("revision must be a non-negative integer")
        with self.lock:
            path = self._path(session)
            current = self.load(session)
            if current["revision"] != expected_revision:
                raise ConflictError(
                    "A newer snapshot exists; export local changes before reloading"
                )
            record = {"revision": current["revision"] + 1, "state": state}
            descriptor, temporary = tempfile.mkstemp(
                prefix=".snapshot-", dir=self.directory
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    json.dump(record, output, ensure_ascii=False, allow_nan=False)
                    output.write("\n")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"revision": record["revision"]}
