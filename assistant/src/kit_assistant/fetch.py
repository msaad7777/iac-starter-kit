"""Download the external docs listed in sources.json at a pinned commit.

Only plain documentation files are fetched (Markdown/MDX), from raw.githubusercontent.com.
The commit SHA of every source is written to data/manifest.json, which is committed, so a
later fetch with --pinned gets byte-identical files.
"""
from __future__ import annotations

import json
import time

import httpx

from . import config

HEADERS = {"User-Agent": "iac-starter-kit-assistant/0.1"}


def resolve_sha(client: httpx.Client, repo: str, branch: str) -> str:
    r = client.get(f"https://api.github.com/repos/{repo}/commits/{branch}", headers={**HEADERS, "Accept": "application/vnd.github.sha"})
    r.raise_for_status()
    return r.text.strip()


def fetch(pinned: bool = False) -> dict:
    sources = json.loads(config.SOURCES.read_text())
    old = json.loads(config.MANIFEST.read_text()) if config.MANIFEST.exists() else {}
    manifest = {"external": []}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for src in sources["external"]:
            prev = next((m for m in old.get("external", []) if m["repo"] == src["repo"]), None)
            sha = prev["sha"] if pinned and prev else resolve_sha(client, src["repo"], src["branch"])
            files = []
            for path in src["paths"]:
                url = f"https://raw.githubusercontent.com/{src['repo']}/{sha}/{path}"
                r = client.get(url, headers=HEADERS)
                if r.status_code != 200:
                    print(f"  missing {src['repo']}:{path} ({r.status_code})")
                    continue
                dest = config.CORPUS / src["repo"].replace("/", "__") / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                files.append({"path": path, "bytes": len(r.content)})
                time.sleep(0.1)
            manifest["external"].append({
                "name": src["name"], "repo": src["repo"], "sha": sha, "licence": src["licence"],
                "files": files,
            })
            print(f"{src['name']}: {len(files)}/{len(src['paths'])} files at {sha[:12]}")
    config.MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
