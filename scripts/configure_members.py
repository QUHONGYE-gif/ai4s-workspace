#!/usr/bin/env python3
"""Publish the isolated server template or create an ordinary Coder member."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class Coder:
    def __init__(self, env_file):
        settings = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                        if line and not line.startswith("#"))
        self.base = f"http://127.0.0.1:{settings['CODER_PORT']}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.token = None
        self.token = self.api("POST", "/api/v2/users/login", {
            "email": settings["CODER_BOOTSTRAP_EMAIL"],
            "password": settings["CODER_BOOTSTRAP_PASSWORD"],
        })["session_token"]

    def api(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Coder-Session-Token"] = self.token
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with self.opener.open(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else None


def add_member(client, args):
    if not re.fullmatch(r"[a-z]{3}", args.initials):
        raise ValueError("initials must be three lowercase letters")
    if not args.name.strip() or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", args.email):
        raise ValueError("Provide the confirmed member name and login email")
    try:
        existing = client.api("GET", "/api/v2/users/" + args.initials)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        if existing["email"].casefold() != args.email.casefold():
            raise ValueError("Initials already belong to another email; coordinate a unique name")
        print(f"Member {args.initials} already exists; password and roles unchanged.")
        return
    organizations = client.api("GET", "/api/v2/users/me/organizations")
    if len(organizations) != 1:
        raise ValueError("Expected one organization; inspect organization selection first")
    args.credentials_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = args.credentials_dir / f"{args.initials}.json"
    password = secrets.token_urlsafe(24)
    record = {"username": args.initials, "name": args.name, "email": args.email,
              "password": password, "status": "pending", "url": client.base}
    # Reserve a private record before sending the request; never overwrite credentials.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
    user = client.api("POST", "/api/v2/users", {
        "username": args.initials, "name": args.name, "email": args.email,
        "password": password, "login_type": "password", "roles": [],
        "organization_ids": [organizations[0]["id"]],
    })
    record.update(status="created", user_id=user["id"])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(f"Created ordinary member {args.initials}. Private credential file: {path}")


def publish_template(client, args):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name in ("main.tf", "startup.sh", ".terraform.lock.hcl"):
            tar.add(ROOT / "coder/templates/server-personal" / name, arcname=name)
    env = dict(os.environ, CODER_SESSION_TOKEN=client.token)
    cli = [
        "docker", "--host", "unix:///data1/qhy/docker-ai4s/run/docker.sock",
        "exec", "-i", "--env", "CODER_SESSION_TOKEN", "--env", "CODER_URL=http://localhost:7080",
        "ai4s-server-coder-1", "/opt/coder",
    ]
    subprocess.run(cli + ["templates", "push", "server-personal",
        "--directory", "-", "--var", f"seed_path={args.seed_path}", "--yes",
    ], input=archive.getvalue(), env=env, check=True, timeout=300)
    # The legacy prototype mounts deployment credentials: ordinary members must
    # not be able to create workspaces from it. Existing owner workspaces remain.
    subprocess.run(cli + ["templates", "edit", "server-docker", "--private", "--yes"],
                   env=env, check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Create an ordinary member; never grant admin roles")
    add.add_argument("--initials", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--email", required=True)
    add.add_argument("--credentials-dir", type=Path, default=ROOT / ".local/members")
    publish = commands.add_parser("publish-template", help="Run on the configured server")
    publish.add_argument("--seed-path", required=True)
    args = parser.parse_args()
    client = Coder(args.env_file)
    if args.command == "add":
        add_member(client, args)
    else:
        publish_template(client, args)


if __name__ == "__main__":
    main()
