#!/usr/bin/env python3
"""Check the prototype workspace, including an actual stop/start cycle."""

from datetime import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    args = parser.parse_args()
    compose_args = []
    if args.server:
        os.environ["DOCKER_HOST"] = "unix:///data1/qhy/docker-ai4s/run/docker.sock"
        compose_args = ["-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.server.yaml")]
    settings = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                    if line and not line.startswith("#"))
    base = f"http://127.0.0.1:{settings['CODER_PORT']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = None

    def api(method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Coder-Session-Token", token)
        with opener.open(req, timeout=15) as response:
            return json.loads(response.read())

    info = api("GET", "/api/v2/buildinfo")
    token = api("POST", "/api/v2/users/login", {
        "email": settings["CODER_BOOTSTRAP_EMAIL"],
        "password": settings["CODER_BOOTSTRAP_PASSWORD"],
    })["session_token"]
    env = dict(os.environ, CODER_SESSION_TOKEN=token)
    cli = ["docker", "compose", "--project-directory", str(ROOT), *compose_args, "exec", "-T",
           "--env", "CODER_SESSION_TOKEN", "--env", "CODER_URL=http://localhost:7080",
           "coder", "/opt/coder"]

    def run_cli(*args):
        result = subprocess.run(cli + list(args), env=env, cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        with (ROOT / ".local/workspace-check.log").open("a") as log:
            log.write(result.stdout)
        if result.returncode:
            raise RuntimeError(f"Coder command failed: {args[0]}; see .local/workspace-check.log")
        return result.stdout

    path = "/api/v2/users/me/workspace/prototype"
    try:
        workspace = api("GET", path)
        if workspace["latest_build"]["status"] != "running":
            run_cli("start", "prototype", "--yes")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        run_cli("create", "prototype", "--template", "server-docker" if args.server else "local-docker", "--yes")

    def wait_agent():
        for _ in range(90):
            workspace = api("GET", path)
            resources = workspace["latest_build"].get("resources") or []
            agents = [a for r in resources for a in (r.get("agents") or [])]
            if agents and all(a["status"] == "connected" for a in agents):
                return workspace
            if workspace["latest_build"]["status"] == "failed":
                raise RuntimeError("Workspace build failed")
            time.sleep(1)
        raise RuntimeError("Workspace agent did not connect")

    workspace = wait_agent()
    probe = """import hashlib,json,pathlib,tempfile
root=pathlib.Path('/workspace/project')
paths=[]
for base in [pathlib.Path.home(),pathlib.Path('/shared'),root/'.local']:
    d=pathlib.Path(tempfile.mkdtemp(prefix='ai4s-probe-',dir=base))
    p=d/'marker'; p.write_text('persisted'); paths.append(str(p))
print(json.dumps({'paths':paths,'readme_sha256':hashlib.sha256((root/'README.md').read_bytes()).hexdigest()}))
"""
    output = run_cli("ssh", "prototype", "--", "python -c " + shlex.quote(probe))
    evidence = next(json.loads(line) for line in output.splitlines() if line.startswith('{"paths":'))
    assert evidence["readme_sha256"] == hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest()
    print("Coder SSH connection, repository read/write, home and shared writes passed.", flush=True)

    run_cli("stop", "prototype", "--yes")
    run_cli("start", "prototype", "--yes")
    workspace = wait_agent()
    verify = "import pathlib; paths=" + repr(evidence["paths"]) + "; "
    verify += "assert all(pathlib.Path(p).read_text()=='persisted' for p in paths); "
    verify += "[(pathlib.Path(p).unlink(),pathlib.Path(p).parent.rmdir()) for p in paths]; print('PERSISTENCE_OK')"
    output = run_cli("ssh", "prototype", "--", "python -c " + shlex.quote(verify))
    assert "PERSISTENCE_OK" in output
    record = {
        "checked_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "coder_version": info["version"], "workspace_id": workspace["id"],
        "workspace": settings["CODER_BOOTSTRAP_USERNAME"] + "/prototype", "agent_status": "connected",
        "checks": ["authenticated_api", "coder_ssh", "repository_read_write",
                   "home_persistence", "shared_persistence", "workspace_stop_start"],
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT / "compose.yaml", ROOT / "coder/templates/local-docker/main.tf",
                                    ROOT / "docker/workspace/Dockerfile"]},
    }
    (ROOT / ".local/initialization.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Workspace stop/start and persistence passed. Record: .local/initialization.json")


if __name__ == "__main__":
    main()
