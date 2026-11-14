"""Deterministic fixture for checking a committed policy without files or tasks."""

# An eligible cached result takes 6 seconds to transfer or 40 seconds to recompute.
TRANSFER_SECONDS = 6
# Old and cheap to replace, expensive to replace, recently used.
COPIES = (
    {"name": "示例 A", "size_bytes": 3_000_000, "last_used": 1, "recompute_seconds": 300, "uses": 8},
    {"name": "示例 B", "size_bytes": 4_000_000, "last_used": 2, "recompute_seconds": 10, "uses": 1},
    {"name": "示例 C", "size_bytes": 3_000_000, "last_used": 3, "recompute_seconds": 30, "uses": 3},
)


def simulate(config):
    mode = config["reuse_policy"]
    limit = config["transfer_limit_seconds"]
    if mode == "new_sample":
        action = "new_sample"
    elif mode == "force_rerun" or (limit is not None and TRANSFER_SECONDS > limit):
        action = "rerun"
    else:
        action = "reuse"

    def eviction_order(copy):
        if config["retention"] == "lru":
            return copy["last_used"]
        # Fixture score only. The engine team's retention algorithm is independent.
        return copy["recompute_seconds"] * copy["uses"] / copy["size_bytes"]

    occupied = sum(copy["size_bytes"] for copy in COPIES)
    evicted = []
    budget = config["storage_limit_bytes"]
    if budget is not None:
        for copy in sorted(COPIES, key=eviction_order):
            if occupied <= budget:
                break
            occupied -= copy["size_bytes"]
            evicted.append(copy["name"])
    return {"action": action, "transfer_seconds": TRANSFER_SECONDS,
            "initial_bytes": sum(copy["size_bytes"] for copy in COPIES),
            "retained_bytes": occupied, "evicted": evicted}
