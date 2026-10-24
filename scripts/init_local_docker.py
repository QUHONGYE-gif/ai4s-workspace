#!/usr/bin/env python3
"""Initialize this repository's local Docker + Coder prototype."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT)]


def run(*args, env=None):
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if args.server:
        COMPOSE.extend(
            ["-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.server.yaml")]
        )
        os.environ["DOCKER_HOST"] = "unix:///data1/qhy/docker-ai4s/run/docker.sock"
    env_path = ROOT / ".env"
    if args.server and not env_path.exists():
        raise RuntimeError("Create the server-specific .env before starting")
    if not env_path.exists():
        env_path.write_text(
            "CODER_IMAGE=ghcr.io/coder/coder:2.38.0\n"
            "CODER_PORT=7080\n"
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
            "CODER_BOOTSTRAP_USERNAME=local-admin\n"
            "CODER_BOOTSTRAP_EMAIL=local-admin@ai4s.local\n"
            f"CODER_BOOTSTRAP_PASSWORD={secrets.token_urlsafe(24)}\n"
            "AI4S_HTTP_PROXY=\n"
        )
        env_path.chmod(0o600)
    settings = dict(
        line.split("=", 1)
        for line in env_path.read_text().splitlines()
        if line and not line.startswith("#")
    )
    if args.server and settings.get("AI4S_PUBLIC_URL"):
        COMPOSE.extend(["-f", str(ROOT / "compose.https.yaml")])
    prefix = "ai4s-server" if args.server else "ai4s-local"
    template = "server-docker" if args.server else "local-docker"
    workspace_image = (
        "ai4s-workspace:server-0.1.0" if args.server else "ai4s-workspace:0.1.0"
    )
    if not args.server:
        run(sys.executable, str(ROOT / "scripts/cache_terraform_providers.py"))
    run(*COMPOSE, "config", "--quiet")
    proxy = settings.get("AI4S_HTTP_PROXY", "")
    if not args.skip_build:
        run(
            "docker",
            "build",
            "--tag",
            workspace_image,
            "--build-arg",
            f"USER_UID={1000 if args.server else os.getuid()}",
            "--build-arg",
            f"HTTP_PROXY={proxy}",
            "--build-arg",
            f"HTTPS_PROXY={proxy}",
            str(ROOT / "docker/workspace"),
        )
    run("docker", "volume", "create", f"{prefix}_shared")
    run(
        "docker",
        "run",
        "--rm",
        "--user",
        "0",
        "--volume",
        f"{prefix}_shared:/shared",
        workspace_image,
        "chown",
        "0:0" if args.server else f"{os.getuid()}:1000",
        "/shared",
    )
    run(*COMPOSE, "up", "--detach", "--wait", "--wait-timeout", "90")

    base = f"http://127.0.0.1:{settings['CODER_PORT']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        with opener.open(req, timeout=10) as response:
            body = response.read()
            return json.loads(body) if body else None

    # Initial schema migration on the server HDD can take substantially longer.
    for _ in range(180 if args.server else 60):
        try:
            api("GET", "/api/v2/buildinfo")
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    else:
        raise RuntimeError("Coder HTTP endpoint did not become ready")

    try:
        api("GET", "/api/v2/users/first")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        api(
            "POST",
            "/api/v2/users/first",
            {
                "email": settings["CODER_BOOTSTRAP_EMAIL"],
                "username": settings["CODER_BOOTSTRAP_USERNAME"],
                "name": (
                    "Server AI4S Administrator"
                    if args.server
                    else "Local AI4S Administrator"
                ),
                "password": settings["CODER_BOOTSTRAP_PASSWORD"],
                "trial": False,
            },
        )
    login = api(
        "POST",
        "/api/v2/users/login",
        {
            "email": settings["CODER_BOOTSTRAP_EMAIL"],
            "password": settings["CODER_BOOTSTRAP_PASSWORD"],
        },
    )
    cli_env = dict(os.environ, CODER_SESSION_TOKEN=login["session_token"])
    cli = COMPOSE + [
        "exec",
        "-T",
        "--env",
        "CODER_SESSION_TOKEN",
        "--env",
        "CODER_URL=http://localhost:7080",
        "coder",
        "/opt/coder",
    ]
    variables = [
        "--var",
        f"project_path={ROOT}",
        "--var",
        f"deployment_prefix={prefix}",
        "--var",
        f"workspace_image={workspace_image}",
        "--var",
        f"access_port={settings['CODER_PORT']}",
    ]
    if args.server:
        variables.extend(["--var", "workspace_user=0:0"])
    run(
        *cli,
        "templates",
        "push",
        template,
        "--directory",
        "/templates/local-docker",
        *variables,
        "--yes",
        env=cli_env,
    )
    print(f"Coder initialized at {base}; local login credentials are in .env.")
    print(f"Template {template} is ready. Create the prototype workspace in Coder.")


if __name__ == "__main__":
    main()
