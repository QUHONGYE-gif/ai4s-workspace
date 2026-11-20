"""把飞书知识库导出到本地，便于离线查阅。

用法：
    python scripts/feishu_sync.py tree                                  # 只打印目录树
    python scripts/feishu_sync.py pull --out docs/feishu                # 导出正文为 .md
    python scripts/feishu_sync.py pull --node <node_token> --out <dir>  # 只导出某个子树

凭证来自 ~/.lark-cli/config.json（appId / appSecret）；只用标准库。
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BASE = "https://open.feishu.cn/open-apis"
CONFIG = Path.home() / ".lark-cli/config.json"
ROOT_NODE = "ASW0wGtGBiycegkT9bFcqNj2nBf"  # AI4S工作台


def credentials():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    app = data["apps"][0]
    return app["appId"], app["appSecret"]


def tenant_token():
    app_id, app_secret = credentials()
    request = urllib.request.Request(
        BASE + "/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    if body.get("code") != 0:
        raise SystemExit("换取 token 失败: " + json.dumps(body, ensure_ascii=False))
    return body["tenant_access_token"]


def get(path, token, params=None):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{key}={value}" for key, value in params.items())
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    if body.get("code") != 0:
        raise SystemExit(f"接口失败 {path}: {body.get('code')} {body.get('msg')}")
    return body.get("data") or {}


def children(token, space_id, parent):
    items = []
    page_token = ""
    while True:
        params = {"page_size": 50, "parent_node_token": parent}
        if page_token:
            params["page_token"] = page_token
        data = get(f"/wiki/v2/spaces/{space_id}/nodes", token, params)
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            return items
        page_token = data.get("page_token") or ""
        if not page_token:
            return items


def walk(token, space_id, parent, depth, lines, docs):
    for node in children(token, space_id, parent):
        kind = node.get("obj_type")
        label = "docx" if kind == "docx" else f"[{kind}]"
        lines.append(f"{'  ' * depth}- [{label}] {node['title']}  ({node['node_token']})")
        docs.append((depth, node))
        if node.get("has_child"):
            walk(token, space_id, node["node_token"], depth + 1, lines, docs)


def raw_content(token, document_id):
    return get(f"/docx/v1/documents/{document_id}/raw_content", token).get("content", "")


def pull(token, space_id, root_node, out_dir):
    lines, docs = [], []
    walk(token, space_id, root_node, 0, lines, docs)
    for _, node in docs:
        if node.get("obj_type") != "docx":
            continue
        text = raw_content(token, node["obj_token"])
        target = out_dir / (node["title"].replace("/", "_") + ".md")
        target.write_text(text, encoding="utf-8")
        print(f"导出 {target.name}  {len(text)} 字")
    (out_dir / "_tree.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n目录树 {len(docs)} 个节点，正文写入 {out_dir}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="飞书知识库导出工具")
    parser.add_argument("command", choices=("tree", "pull"))
    parser.add_argument("--node", default=ROOT_NODE)
    parser.add_argument("--out", type=Path, default=Path("docs/feishu"))
    args = parser.parse_args()

    token = tenant_token()
    node = get("/wiki/v2/spaces/get_node", token, {"token": args.node})["node"]
    space_id = node["space_id"]

    if args.command == "tree":
        lines, docs = [], []
        walk(token, space_id, args.node, 0, lines, docs)
        print(f"知识库 {space_id} / 根节点 {args.node}")
        print("\n".join(lines))
        print(f"\n共 {len(docs)} 个节点")
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        pull(token, space_id, args.node, args.out)


if __name__ == "__main__":
    main()
