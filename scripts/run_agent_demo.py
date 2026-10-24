#!/usr/bin/env python3
"""Run from the repository root: uv run python scripts/run_agent_demo.py."""

import argparse

import uvicorn

from ai4s_demo.app import create_app


def main():
    parser = argparse.ArgumentParser(description="AI4S Agent 工作流接入演示（单进程）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
