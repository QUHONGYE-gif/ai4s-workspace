# -*- coding: utf-8 -*-
"""从 index.html 中抽出策略说明图，导出为独立 SVG（供幻灯片复用）。

单一来源是 index.html 里的 <!-- SVG-SOURCE-START --> 区块；
改图只改页面，再跑一次本脚本。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"
OUT = ROOT / "policy-diagram.svg"
START = "<!-- SVG-SOURCE-START -->"
END = "<!-- SVG-SOURCE-END -->"


def main():
    html = PAGE.read_text(encoding="utf-8")
    svg = html[html.index(START) + len(START):html.index(END)].strip()
    svg = svg.replace('width="100%"', 'width="1100" height="500"', 1)
    svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"
    OUT.write_text(svg, encoding="utf-8")
    print(f"saved {OUT.name} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
