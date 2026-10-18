#!/usr/bin/env python3
"""Cache checksum-verified Terraform providers for a selected Linux platform."""

import argparse
import hashlib
import json
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = (("coder", "coder", "2.19.0"), ("kreuzwerker", "docker", "3.9.0"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", choices=["arm64", "amd64"], default="arm64")
    parser.add_argument("--output", type=Path, default=ROOT / ".local")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=(429, 502, 503, 504)
    )))
    manifest = args.output / "provider-manifest.json"
    cached = json.loads(manifest.read_text()) if manifest.exists() else []
    records = []
    for namespace, name, version in PROVIDERS:
        folder = args.output / "provider-mirror/registry.terraform.io" / namespace / name
        target = folder / f"terraform-provider-{name}_{version}_linux_{args.arch}.zip"
        previous = next((item for item in cached if item["provider"] == f"{namespace}/{name}"
                         and item["version"] == version and item["platform"] == f"linux_{args.arch}"), None)
        if previous and target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == previous["sha256"]:
            records.append(previous)
            print(f"Verified cached {target.name}", flush=True)
            continue
        endpoint = f"https://registry.terraform.io/v1/providers/{namespace}/{name}/{version}/download/linux/{args.arch}"
        response = session.get(endpoint, timeout=60)
        response.raise_for_status()
        metadata = response.json()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / metadata["filename"]
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != metadata["shasum"]:
            download = session.get(metadata["download_url"], stream=True, timeout=(30, 120))
            download.raise_for_status()
            partial = target.with_suffix(".part")
            checksum = hashlib.sha256()
            with partial.open("wb") as output:
                for chunk in download.iter_content(1024 * 1024):
                    checksum.update(chunk)
                    output.write(chunk)
            if checksum.hexdigest() != metadata["shasum"]:
                raise RuntimeError(f"Checksum mismatch for {target.name}")
            partial.replace(target)
        print(f"Verified {target.name}", flush=True)
        records.append({"provider": f"{namespace}/{name}", "version": version,
                        "platform": f"linux_{args.arch}", "sha256": metadata["shasum"]})
    manifest.write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
