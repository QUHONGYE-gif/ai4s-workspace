#!/usr/bin/env python3
"""Start the Agent service; the existing workspace launcher owns joint startup."""

import argparse
from pathlib import Path
import sys

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai4s_demo.app import create_app


def main():
    parser = argparse.ArgumentParser(description="AI4S Agent 工作流接入服务（单进程）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--root-path", default="/agent", help="反向代理移除的页面路径前缀")
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port,
                root_path=args.root_path, workers=1)


if __name__ == "__main__":
    main()
