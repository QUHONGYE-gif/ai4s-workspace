"""Read the workspace's committed policy without importing AiiDA."""

import json
import os
from pathlib import Path

DEFAULT_POLICY = {
    "reuse_policy": "allow_reuse",
    "transfer_limit_seconds": None,
    "storage_limit_bytes": None,
    "retention": "lru",
}


def read_policy(data_dir):
    path = Path(data_dir) / "policies" / "workspace.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"config": DEFAULT_POLICY.copy(), "revision": 0, "history": []}


def workspace_actor():
    owner = os.environ.get("CODER_WORKSPACE_OWNER")
    return {
        "member_id": os.environ.get("AI4S_POLICY_MEMBER_ID") or owner or "local",
        "display_name": os.environ.get("AI4S_POLICY_MEMBER_NAME") or owner or "本地工作区",
    }
