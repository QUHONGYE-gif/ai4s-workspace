"""Registration catalog facts; adapter source support is not runtime availability."""


def task_catalog(registry):
    tasks = {}
    for item in registry.list():
        document = registry.get(item["task_id"], item["version"])
        task = tasks.setdefault(item["task_id"], {
            "task_id": item["task_id"],
            "name": document["name"],
            "model_id": document["model"]["model_id"],
            "versions": [],
        })
        task["versions"].append({
            **item,
            "definition_status": "repository_loaded",
            "adapter_status": (
                "source_supported"
                if document["task_id"] == "proteinmpnn"
                and document["execution"].get("calculation_entry_point") == "ai4s.proteinmpnn"
                and document["execution"].get("workflow_entry_point") == "ai4s.protein-mpnn-filter"
                else "unsupported"
            ),
            "execution": document["execution"],
            "web_execution_connected": False,
        })
    return {
        "tasks": list(tasks.values()),
        "planned": [
            {"task_id": "rfdiffusion", "name": "RFdiffusion", "purpose": "蛋白质骨架生成"},
            {"task_id": "boltz", "name": "Boltz", "purpose": "结构预测"},
            {"task_id": "mmseqs2", "name": "MMseqs2", "purpose": "序列搜索与比对"},
        ],
        "engine_status": "not_connected",
    }
