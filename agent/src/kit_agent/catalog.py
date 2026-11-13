"""Read the kit's modules and their variables straight from modules/*/variables.tf.

The agent may only compose these. A module with no `resource` block (tags) is left out:
root.hcl already applies the standard tags through provider default_tags."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Inputs the unit never sets itself: root.hcl passes region and environment to every unit,
# and gpu-inference gets its subnets from a dependency on a network unit.
INJECTED = {"region", "environment"}
DEPENDENCY_INPUTS = {"gpu-inference": {"subnet_ids"}}


@dataclass
class Variable:
    name: str
    type: str
    required: bool
    description: str


@dataclass
class Module:
    name: str
    variables: dict[str, Variable] = field(default_factory=dict)

    def settable(self) -> dict[str, Variable]:
        hidden = INJECTED | DEPENDENCY_INPUTS.get(self.name, set())
        return {k: v for k, v in self.variables.items() if k not in hidden}

    def required(self) -> set[str]:
        return {k for k, v in self.settable().items() if v.required}


def _blocks(text: str, keyword: str) -> list[tuple[str, str]]:
    """Return (label, body) for every `keyword "label" { ... }` block, matching braces."""
    out = []
    for m in re.finditer(rf'^{keyword}\s+"([^"]+)"\s*\{{', text, re.M):
        depth, i = 1, m.end()
        while depth and i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append((m.group(1), text[m.end():i - 1]))
    return out


def _description(body: str) -> str:
    m = re.search(r'^\s*description\s*=\s*"((?:[^"\\]|\\.)*)"', body, re.M)
    if m:
        return m.group(1)
    m = re.search(r'^\s*description\s*=\s*<<-?(\w+)\n(.*?)\n\s*\1', body, re.M | re.S)
    return " ".join(m.group(2).split()) if m else ""


def _type(body: str) -> str:
    m = re.search(r"^\s*type\s*=\s*(.+)$", body, re.M)
    if not m:
        return "any"
    t = m.group(1).strip()
    if t.startswith("object("):
        fields = re.findall(r"^\s+(\w+)\s*=\s*\w+", body[m.end():body.find("})", m.end())], re.M)
        return "object{" + ",".join(fields) + "}"
    allowed = re.search(r"contains\(\[([^\]]+)\],\s*var\.", body)
    if allowed:
        return t + " " + "|".join(x.strip().strip('"') for x in allowed.group(1).split(","))
    return t


def parse_variables(text: str) -> dict[str, Variable]:
    out = {}
    for name, body in _blocks(text, "variable"):
        # Only a top-level `default` counts; validation blocks never contain one.
        required = re.search(r"^\s{2}default\s*=", body, re.M) is None
        out[name] = Variable(name, _type(body), required, _description(body))
    return out


def load(kit_root: Path) -> dict[str, Module]:
    modules = {}
    for d in sorted((kit_root / "modules").iterdir()):
        main, variables = d / "main.tf", d / "variables.tf"
        if not (main.is_file() and variables.is_file()):
            continue
        if not re.search(r'^resource\s+"', main.read_text(), re.M):
            continue
        modules[d.name] = Module(d.name, parse_variables(variables.read_text()))
    return modules


def describe(modules: dict[str, Module]) -> str:
    """Compact text for the model: one line per variable, * marks required."""
    lines = []
    for m in modules.values():
        lines.append(f"{m.name}:")
        for v in m.settable().values():
            desc = re.split(r"[.(,]", v.description)[0].strip()[:55] if v.name != "tags" else ""
            lines.append(f" {v.name}{'*' if v.required else ''} {v.type}" + (f" - {desc}" if desc else ""))
        if m.name in DEPENDENCY_INPUTS:
            lines.append(" (subnets: pass network_unit, a network unit in the same env)")
    return "\n".join(lines)
