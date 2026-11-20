"""飞书用户身份登录（OAuth 授权码流程），token 存本地文件。

不依赖 lark-cli 的凭据存储（那台机器上 keychain/锁不可用）。

用法：
    python scripts/feishu_user_login.py

流程：
    1. 本地起 http://127.0.0.1:8765 接收回调
    2. 打印授权链接，浏览器打开并同意
    3. 收到 code 后换 user_access_token，写入 .local/feishu-user-token.json

前提：开放平台 → 安全设置 → 重定向 URL 里已添加 http://127.0.0.1:8765/callback
"""

import json
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

APP_ID = "cli_aa7562cd2eb8dd29"
REDIRECT = "http://127.0.0.1:8765/callback"
SCOPE = "wiki:wiki:readonly docx:document:readonly"
CONFIG = Path.home() / ".lark-cli/config.json"
TOKEN_FILE = Path(".local/feishu-user-token.json")
AUTHORIZE = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"


def app_secret():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data["apps"][0]["appSecret"]


result = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.parse_qs(parsed.query)
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]
        result["code"] = code
        result["error"] = error
        body = "<h2>授权完成，可以关闭此页面回到终端</h2>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def exchange(code):
    payload = {
        "grant_type": "authorization_code",
        "client_id": APP_ID,
        "client_secret": app_secret(),
        "code": code,
        "redirect_uri": REDIRECT,
    }
    request = urllib.request.Request(
        TOKEN_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def main():
    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "app_id": APP_ID, "redirect_uri": REDIRECT, "scope": SCOPE, "state": "ai4s"})
    print("在浏览器打开下面的链接并同意授权：\n")
    print(url)
    print()
    webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("等待回调 http://127.0.0.1:8765/callback ...")
    server.serve_forever()
    if result.get("error"):
        raise SystemExit("授权失败：" + result["error"])
    body = exchange(result["code"])
    if body.get("code") not in (0, None):
        raise SystemExit("换取 token 失败：" + json.dumps(body, ensure_ascii=False)[:400])
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已保存到", TOKEN_FILE)


if __name__ == "__main__":
    main()
