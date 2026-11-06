"""Create query examples in the selected AiiDA profile; no daemon or model needed."""

import argparse
from datetime import datetime
import io
import json
from pathlib import Path
from uuid import uuid4

from aiida import load_profile
from aiida.engine import run
from aiida.manage.caching import enable_caching
from aiida.orm import FolderData, Int, QueryBuilder, Str
from aiida.orm.nodes.process.process import ProcessNode

from ai4s_query import query, report
from ai4s_query.sample_calcs import filter_by_length, seq_stats, strict_length_check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.home() / "runs" /
                        ("query-demo-" + datetime.now().strftime("%Y%m%d-%H%M%S")),
                        help="New directory for reports and node UUIDs.")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=False)
    load_profile()

    # The two filters share one Data node and produce different results.
    sequence = Str("MKTAYIAKQRQISFVKSHFSRQ")
    stats = run(seq_stats, seq=sequence)
    run(filter_by_length, stats=stats, min_len=Int(10))
    selected = run(filter_by_length, stats=stats, min_len=Int(30))

    with enable_caching():
        run(seq_stats, seq=sequence)
        cached = run(seq_stats, seq=sequence)

    # A unique label identifies our failed process without scanning other runs.
    failure_label = "query-demo-failure-" + uuid4().hex
    try:
        run(strict_length_check, stats=stats, min_len=Int(100),
            metadata={"label": failure_label})
    except ValueError:
        pass
    failed = QueryBuilder().append(ProcessNode, filters={"label": failure_label}).one()[0]

    # This is a generic binary fixture, not a scientific NPZ or model output.
    binary = FolderData()
    binary.base.repository.put_object_from_filelike(io.BytesIO(bytes(range(256))), "payload.bin")
    binary.label = "查询示例：无 creator 的二进制数据"
    binary.store()

    nodes = {
        "process": selected.creator,
        "cache": cached.creator,
        "shared_data": stats,
        "failure": failed,
        "binary": binary,
    }
    for name, node in nodes.items():
        info = query.describe(node.uuid)
        report.to_text(info, str(options.output / (name + ".txt")))
        report.to_json(info, str(options.output / (name + ".json")))
    steps = query.trace(selected.uuid)
    report.trace_text(steps, str(options.output / "trace.txt"))
    report.to_json({"trace": steps}, str(options.output / "trace.json"))
    index = {name: node.uuid for name, node in nodes.items()}
    index["selected"] = selected.uuid
    (options.output / "nodes.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"Reports: {options.output}")
    print(json.dumps(index, indent=2))


if __name__ == "__main__":
    main()
