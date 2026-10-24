#!/usr/bin/env python3
"""Run from the repository root: uv run python scripts/run_agent_demo.py."""

import argparse
import os
from pathlib import Path
import sys
import threading

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai4s_demo.app import create_app


def main():
    parser = argparse.ArgumentParser(description="AI4S Agent 工作流接入演示（单进程）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--with-workbench", action="store_true", help="在同一预览运行工作台，并以 /agent/ 接入智能体")
    parser.add_argument("--agent-port", type=int, default=3002, help="联合模式下仅监听回环地址的内部端口")
    parser.add_argument("--workbench-data-dir", default=None)
    args = parser.parse_args()
    if args.with_workbench:
        from workbench.server import create_server

        if args.agent_port == args.port:
            parser.error("工作台与内部 Agent 端口不能相同")
        state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        workbench_data = args.workbench_data_dir or state_home / "ai4s-workbench-demo/api-state"
        server = create_server(args.host, args.port, workbench_data, agent_port=args.agent_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Workbench: http://{args.host}:{server.server_port}/ ; Agent: ./agent/", flush=True)
        try:
            uvicorn.run(create_app(args.data_dir, root_path="/agent"), host="127.0.0.1", port=args.agent_port, workers=1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        return
    uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
