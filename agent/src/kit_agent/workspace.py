"""Every file the agent writes goes through this module. The rules are enforced in code,
not left to the model:

- writes land only under live/, never in live/_envcommon or live/root.hcl;
- the agent may create files, or edit files it created in this run, never kit-owned ones;
- a unit can only point at one of the kit's own modules, and only set that module's variables;
- writing under live/prod needs the prod-approved label.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, config

UNIT_NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
OWNER = re.compile(r"^[A-Za-z0-9@._-]{1,64}$")
COST_CENTER = re.compile(r"^CC-[0-9]{4}$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Values that name an existing AWS resource. The agent may only use ones the request gives,
# plus the kit's own placeholder AMI, so it cannot make up a key, role or subnet.
REFERENCE = re.compile(r"^(arn:|ami-|sg-|subnet-|vpc-|key/|alias/)")
# "100 percent on-demand", "70% on demand": a number the request states for the on-demand share.
ON_DEMAND = re.compile(r"(\d{1,3})\s*(?:%|percent)\s*on[- ]demand", re.I)


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


class Refused(Exception):
    """A hard rule was broken. The run ends as a refusal, whatever the model wants next."""


class ToolError(Exception):
    """A fixable mistake. The message goes back to the model."""


def safe_path(root: Path, rel: str) -> Path:
    """Resolve rel inside root/live, or raise. Symlinks and .. are resolved first."""
    live = (root / "live").resolve()
    p = (root / rel).resolve()
    if p == live or live not in p.parents:
        raise Refused(f"write outside live/ refused: {rel}")
    if (live / "_envcommon") in p.parents or p == live / "root.hcl":
        raise Refused(f"shared kit config is not the agent's to edit: {rel}")
    return p


def hcl_string(s: str) -> str:
    # JSON string escapes are valid HCL; also stop ${ and %{ from being read as templates.
    return json.dumps(s).replace("${", "$${").replace("%{", "%%{")


def hcl_value(v, indent: int = 2) -> str:
    pad = " " * indent
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return hcl_string(v)
    if isinstance(v, list):
        return "[" + ", ".join(hcl_value(x, indent) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        keys = [k if IDENT.match(k) else hcl_string(k) for k in v]
        width = max(len(k) for k in keys)
        rows = [f"{pad}  {k.ljust(width)} = {hcl_value(x, indent + 2)}" for k, x in zip(keys, v.values())]
        return "{\n" + "\n".join(rows) + f"\n{pad}}}"
    raise ToolError(f"unsupported value {v!r}")


def render_unit(module: str, inputs: dict, request: str, network_unit: str | None = None) -> str:
    note = " ".join(request.split())[:110].replace("*/", "")
    lines = [
        "# Written by kit-agent. Request:",
        f"#   {note}",
        'include "root" {',
        '  path = find_in_parent_folders("root.hcl")',
        "}",
        "",
        "terraform {",
        f'  source = "${{get_repo_root()}}/modules/{module}"',
        "}",
        "",
    ]
    raw = {}
    if network_unit:
        lines += [
            'dependency "network" {',
            f'  config_path = "../{network_unit}"',
            "",
            "  # Lets plan run before the network exists. Apply always uses the real outputs.",
            "  mock_outputs = {",
            '    private_subnet_ids = ["subnet-00000000000000001", "subnet-00000000000000002"]',
            "  }",
            '  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]',
            "}",
            "",
        ]
        raw["subnet_ids"] = "dependency.network.outputs.private_subnet_ids"
    keys = list(inputs) + list(raw)
    width = max((len(k) for k in keys), default=0)
    body = [f"  {k.ljust(width)} = {hcl_value(v)}" for k, v in inputs.items()]
    body += [f"  {k.ljust(width)} = {v}" for k, v in raw.items()]
    lines += ["inputs = {", *body, "}", ""]
    return "\n".join(lines)


def format_hcl(text: str) -> str:
    """Canonical format through terragrunt when it is installed (CI checks it); else as is."""
    if not shutil.which("terragrunt"):
        return text
    r = subprocess.run(["terragrunt", "hcl", "format", "--stdin", "--log-level", "error"],
                       input=text, capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 and r.stdout.strip() else text


@dataclass
class Workspace:
    root: Path
    request: str
    labels: list[str] = field(default_factory=list)
    modules: dict[str, catalog.Module] = field(default_factory=dict)
    written: dict[str, dict] = field(default_factory=dict)   # rel path -> what was written
    dirty: bool = False                                      # written since the last gate run

    def __post_init__(self):
        self.root = Path(self.root).resolve()
        if not self.modules:
            self.modules = catalog.load(self.root)

    # ---- helpers -------------------------------------------------------------------------
    def placeholder_ami(self) -> str:
        """The kit's own placeholder AMI, from live/_envcommon/llm-inference.hcl."""
        f = self.root / "live/_envcommon/llm-inference.hcl"
        m = re.search(r'ami_id\s*=\s*"(ami-[0-9a-f]+)"', f.read_text()) if f.is_file() else None
        return m.group(1) if m else ""

    def env_dir(self, env: str) -> Path:
        if env not in config.ENVIRONMENTS:
            raise ToolError(f"env must be one of {', '.join(config.ENVIRONMENTS)}")
        if env == "prod" and config.PROD_APPROVAL_LABEL not in self.labels:
            raise Refused(f"prod changes need the '{config.PROD_APPROVAL_LABEL}' label on the request")
        return safe_path(self.root, f"live/{env}/env.hcl").parent

    def envs(self) -> dict[str, bool]:
        return {e: (self.root / "live" / e / "env.hcl").is_file() for e in config.ENVIRONMENTS}

    def touched_envs(self) -> list[str]:
        return sorted({rel.split("/")[1] for rel in self.written})

    def _write(self, rel: str, text: str, meta: dict) -> str:
        p = safe_path(self.root, rel)
        if p.exists() and rel not in self.written:
            raise ToolError(f"{rel} already exists and belongs to the kit; pick another unit name")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.written[rel] = meta
        self.dirty = True
        return rel

    # ---- tools ---------------------------------------------------------------------------
    def create_env(self, env: str, owner: str, cost_center: str) -> dict:
        d = self.env_dir(env)
        if (d / "env.hcl").exists() and f"live/{env}/env.hcl" not in self.written:
            raise ToolError(f"env {env} already exists; write units into it directly")
        if not OWNER.match(owner or ""):
            raise ToolError("owner must be a team handle like payments-team")
        if not COST_CENTER.match(cost_center or ""):
            raise ToolError("cost_center must look like CC-1234")
        env_hcl = (f'locals {{\n  environment = "{env}"\n  cost_center = "{cost_center}"\n'
                   f'  owner       = "{owner}"\n}}\n')
        region_hcl = f'locals {{\n  aws_region = "{config.REGION}"\n}}\n'
        a = self._write(f"live/{env}/env.hcl", env_hcl, {"kind": "env", "owner": owner, "cost_center": cost_center})
        b = self._write(f"live/{env}/{config.REGION}/region.hcl", region_hcl, {"kind": "region"})
        return {"ok": True, "wrote": [a, b]}

    def write_unit(self, env: str, unit: str, module: str, inputs: dict | None = None,
                   network_unit: str | None = None) -> dict:
        d = self.env_dir(env)
        if not (d / "env.hcl").exists():
            raise ToolError(f"env {env} does not exist yet; call create_env first")
        if not UNIT_NAME.match(unit or ""):
            raise ToolError("unit must be lowercase letters, digits and hyphens, like payments-bucket")
        if module not in self.modules:
            raise Refused(f"unknown module '{module}': the agent only composes {', '.join(self.modules)}")
        inputs = dict(inputs or {})
        mod = self.modules[module]
        unknown = set(inputs) - set(mod.settable())
        if unknown:
            raise ToolError(f"{module} has no variable(s) {', '.join(sorted(unknown))}")
        missing = mod.required() - set(inputs)
        if missing:
            raise ToolError(f"{module} needs {', '.join(sorted(missing))}")
        allowed_refs = {self.placeholder_ami()}
        for value in _strings(inputs):
            if REFERENCE.match(value) and value not in self.request and value not in allowed_refs:
                raise ToolError(f"{value} is not in the request: never invent IDs or ARNs, leave that variable unset")
        stated = {int(n) for n in ON_DEMAND.findall(self.request)}
        pct = inputs.get("on_demand_percentage_above_base")
        if module == "gpu-inference" and stated and pct is not None and int(pct) not in stated:
            # eval run 2, ref-07: asked for 100 percent, silently wrote 50 and opened a PR
            raise ToolError(f"the request states {', '.join(map(str, sorted(stated)))} percent on-demand; do not "
                            "change it. If that breaks a policy, call refuse.")
        if module == "budget" and inputs.get("anomaly_detection") is True:
            raise ToolError("AWS allows one anomaly monitor per account and the prod budget owns it: "
                            "leave anomaly_detection unset")
        needs_net = module in catalog.DEPENDENCY_INPUTS
        if needs_net and not network_unit:
            raise ToolError(f"{module} needs network_unit: the name of a network unit in {env}")
        if not needs_net:
            network_unit = None
        if network_unit and not UNIT_NAME.match(network_unit):
            raise ToolError("network_unit must be a unit name")
        rel = f"live/{env}/{config.REGION}/{unit}/terragrunt.hcl"
        text = format_hcl(render_unit(module, inputs, self.request, network_unit))
        self._write(rel, text, {"kind": "unit", "env": env, "unit": unit, "module": module,
                                "inputs": inputs, "network_unit": network_unit})
        return {"ok": True, "wrote": rel}

    def delete_unit(self, env: str, unit: str) -> dict:
        rel = f"live/{env}/{config.REGION}/{unit}/terragrunt.hcl"
        if rel not in self.written:
            raise ToolError(f"{rel} was not written by this run; the agent only removes its own units")
        p = safe_path(self.root, rel)
        p.unlink()
        if not any(p.parent.iterdir()):
            p.parent.rmdir()
        del self.written[rel]
        self.dirty = True
        return {"ok": True, "deleted": rel}

    def read_unit(self, env: str, unit: str) -> dict:
        p = safe_path(self.root, f"live/{env}/{config.REGION}/{unit}/terragrunt.hcl")
        if not p.is_file():
            raise ToolError("no such unit")
        return {"ok": True, "text": p.read_text()[:3000]}

    def units(self) -> list[dict]:
        return [m for m in self.written.values() if m["kind"] == "unit"]
