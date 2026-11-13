"""One git worktree and branch per request, so the agent never touches your checkout.

Only the units the agent wrote and the ADR and diagram the pipeline drew are committed. Nothing is pushed; opening the PR is a human step."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from . import config

AUTHOR = (os.getenv("AGENT_GIT_NAME", "kit-agent"), os.getenv("AGENT_GIT_EMAIL", "kit-agent@localhost.invalid"))


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].rstrip("-") or "request"


class Worktree:
    def __init__(self, repo: Path, request: str, base: str = "HEAD", prefix: str = config.BRANCH_PREFIX):
        self.repo = Path(repo).resolve()
        self.branch = f"{prefix}{slug(request)}-{uuid.uuid4().hex[:6]}"
        self.path = Path(tempfile.mkdtemp(prefix="kit-agent-")) / "kit"
        git(self.repo, "worktree", "add", "-q", "-b", self.branch, str(self.path), base)

    def commit(self, files: list[str], subject: str, body: str) -> str:
        for f in files:
            if not (f.startswith("live/") or f.startswith("docs/adr/")):
                raise RuntimeError(f"refusing to commit {f}: only live/ and docs/adr/ are allowed")
        git(self.path, "add", "--", *files)
        env = dict(os.environ, GIT_AUTHOR_NAME=AUTHOR[0], GIT_AUTHOR_EMAIL=AUTHOR[1],
                   GIT_COMMITTER_NAME=AUTHOR[0], GIT_COMMITTER_EMAIL=AUTHOR[1])
        git(self.path, "commit", "-q", "-m", subject, "-m", body, env=env)
        return git(self.path, "rev-parse", "HEAD")

    def close(self, keep_branch: bool) -> None:
        subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.path)],
                       capture_output=True)
        shutil.rmtree(self.path.parent, ignore_errors=True)
        subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True)
        if not keep_branch:
            subprocess.run(["git", "-C", str(self.repo), "branch", "-D", self.branch], capture_output=True)
