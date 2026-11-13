"""Run the kit's own gates: scripts/plan-json.sh and scripts/check-policies.sh.

These are the only commands the agent can run. There is no apply anywhere in this package,
and the gates refuse to start unless every AWS call would go to a local mock (Moto or the
AWS Emulator), so a run can never reach real AWS."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PLAN_SCRIPT = "scripts/plan-json.sh"
POLICY_SCRIPT = "scripts/check-policies.sh"


class UnsafeTarget(Exception):
    pass


def local_env(base: dict | None = None) -> dict:
    """Environment for the gate scripts, pointed at a local mock only.

    KIT_TARGET=emulator keeps the AWS Emulator settings from scripts/emulator-env.sh.
    Anything else gets the Moto settings from scripts/moto-env.sh, with throwaway keys."""
    env = dict(base if base is not None else os.environ)
    for k in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        env.pop(k, None)
    if env.get("KIT_TARGET") == "emulator":
        url = env.get("EMULATOR_URL", "https://127.0.0.1:9297")
        env.setdefault("AWS_ENDPOINT_URL", url)
    else:
        url = env.get("MOTO_URL", "http://localhost:5000")
        creds = Path(tempfile.gettempdir()) / "iac-starter-kit-agent-aws"
        creds.mkdir(exist_ok=True)
        (creds / "credentials").write_text("[default]\naws_access_key_id = test\naws_secret_access_key = test\n")
        (creds / "config").write_text("[default]\nregion = us-east-1\n")
        env.update(KIT_TARGET="moto", MOTO_URL=url, AWS_ENDPOINT_URL=url,
                   AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test",
                   AWS_REGION="us-east-1", AWS_DEFAULT_REGION="us-east-1",
                   AWS_SHARED_CREDENTIALS_FILE=str(creds / "credentials"),
                   AWS_CONFIG_FILE=str(creds / "config"))
    assert_local(env)
    env.setdefault("TF_PLUGIN_CACHE_DIR", str(Path.home() / ".terraform.d" / "plugin-cache"))
    Path(env["TF_PLUGIN_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    env["TG_NO_COLOR"] = "true"
    env["TF_IN_AUTOMATION"] = "1"
    return env


def assert_local(env: dict) -> None:
    if env.get("KIT_TARGET") not in ("moto", "emulator"):
        raise UnsafeTarget("KIT_TARGET must be moto or emulator")
    host = urlparse(env.get("AWS_ENDPOINT_URL", "")).hostname
    if host not in LOCAL_HOSTS:
        raise UnsafeTarget(f"AWS_ENDPOINT_URL must be local, got {host!r}")


def _errors(text: str, limit: int = 1500) -> str:
    """Keep the Terraform error blocks and drop Terragrunt's log noise."""
    text = ANSI.sub("", text)
    blocks = re.findall(r"(?:│\s*)?Error: .*?(?=\n\s*\n|\Z)", text, re.S)
    out = "\n".join(re.sub(r"^[│╷╵ ]+", "", ln) for b in blocks for ln in b.splitlines())
    return (out or text[-limit:]).strip()[:limit]


def summarise_plan(path: Path) -> dict:
    data = json.loads(path.read_text())
    counts: dict[str, int] = {}
    types: dict[str, int] = {}
    for rc in data.get("resource_changes", []):
        actions = rc["change"]["actions"]
        key = "no-op" if actions == ["no-op"] else "+".join(actions)
        counts[key] = counts.get(key, 0) + 1
        if key != "no-op" and key != "read":
            types[rc["type"]] = types.get(rc["type"], 0) + 1
    return {"actions": counts, "types": types}


@dataclass
class PlanResult:
    ok: bool
    plans: dict[str, dict] = field(default_factory=dict)
    error: str = ""
    seconds: float = 0.0


@dataclass
class PolicyResult:
    ok: bool
    files: dict[str, dict] = field(default_factory=dict)
    seconds: float = 0.0


def parse_policy_output(text: str) -> dict[str, dict]:
    files, current = {}, None
    for line in ANSI.sub("", text).splitlines():
        if line.startswith("== "):
            current = line[3:].strip()
            files[current] = {"pass": 0, "fail": 0, "violations": []}
        elif current and (m := re.match(r"pass: (\d+), fail: (\d+)", line)):
            files[current]["pass"], files[current]["fail"] = int(m.group(1)), int(m.group(2))
        elif current and re.match(r"^\d+ - ", line):
            files[current]["violations"].append(re.sub(r"^\d+ - (validation )?", "", line).strip())
    return files


class Gates:
    """The real gates. Tests swap in a fake with the same two methods."""

    def __init__(self, env: dict | None = None, timeout_s: int = 900):
        self.env = local_env(env)
        self.timeout_s = timeout_s

    def plan(self, root: Path, envs: list[str]) -> PlanResult:
        import time
        t0 = time.perf_counter()
        plans_dir = root / "plans"
        if plans_dir.exists():
            for f in plans_dir.glob("*.json"):
                f.unlink()
        assert_local(self.env)
        for env in envs:
            r = subprocess.run(["bash", str(root / PLAN_SCRIPT), env], cwd=root, env=self.env,
                               capture_output=True, text=True, timeout=self.timeout_s)
            if r.returncode != 0:
                return PlanResult(False, error=f"plan failed in {env}:\n" + _errors(r.stderr + r.stdout),
                                  seconds=time.perf_counter() - t0)
        plans = {p.stem: summarise_plan(p) for p in sorted(plans_dir.glob("*.json"))}
        return PlanResult(True, plans, seconds=time.perf_counter() - t0)

    def policies(self, root: Path) -> PolicyResult:
        import time
        t0 = time.perf_counter()
        r = subprocess.run(["bash", str(root / POLICY_SCRIPT)], cwd=root, env=self.env,
                           capture_output=True, text=True, timeout=self.timeout_s)
        files = parse_policy_output(r.stdout)
        return PolicyResult(r.returncode == 0 and bool(files), files, seconds=time.perf_counter() - t0)
