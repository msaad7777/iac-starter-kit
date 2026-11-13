"""Draft an architecture decision record (MADR style) for each agent PR.

Code writes the facts: modules used, plan add/change/destroy counts, policy results and the
diagram link. The model writes only the context, the options considered and the rationale,
through one JSON-schema-constrained call with no tools. The ADR is always "Proposed"; CI
(scripts/check-adr-status.sh) blocks the merge until a person changes it."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

ADR_DIR = "docs/adr"
FACTS_HEADER = "## Facts from the plan"

SCHEMA = {
    "type": "object",
    "required": ["context", "options", "chosen", "rationale", "consequences"],
    "properties": {
        "context": {"type": "string"},
        "options": {"type": "array", "items": {"type": "object", "required": ["name", "summary"],
                    "properties": {"name": {"type": "string"}, "summary": {"type": "string"}}}},
        "chosen": {"type": "string"},
        "rationale": {"type": "string"},
        "consequences": {"type": "array", "items": {"type": "string"}},
    },
}

PROMPT = """Write the reasoning sections of an architecture decision record for this infrastructure change. Reply with JSON only, matching the schema.
- context: 2-3 sentences: what was asked and why it needs a decision.
- options: 2 or 3 options that were realistic with this kit's modules, including the chosen one.
- chosen: the name of the chosen option.
- rationale: 2-3 sentences on why, tied to cost, security and the kit's policies.
- consequences: 2-4 short bullets, good and bad.
Do not state numbers of resources; the facts table is added separately.

What the kit's modules always do (do not list these as missing): {defaults}

Request: {request}
Units written: {units}
Agent's reasons: {reasons}"""

# From the kit README's module table; the modules enforce these whatever the inputs are.
MODULE_DEFAULTS = {
    "s3-bucket": "public access blocked, bucket-owner ownership, SSE-S3 encryption (or KMS if given), versioning, lifecycle to Intelligent-Tiering, TLS-only bucket policy",
    "network": "public and private subnets, NAT strategy none/single/per_az, free S3 and DynamoDB gateway endpoints",
    "budget": "monthly AWS Budget filtered by cost centre, alerts at 80% actual and 100% forecast",
    "gpu-inference": "spot-first GPU Auto Scaling group, IMDSv2 required, encrypted gp3 root volume, tags reach instances",
}

FALLBACK = "_(The model gave no usable draft. Write this section before accepting.)_"


def counts(actions: dict[str, int]) -> tuple[int, int, int]:
    """Terraform's own convention: a replace counts as one add and one destroy."""
    add = change = destroy = 0
    for act, n in actions.items():
        parts = act.split("+")
        if parts == ["create"]:
            add += n
        elif parts == ["update"]:
            change += n
        elif parts == ["delete"]:
            destroy += n
        elif set(parts) == {"create", "delete"}:
            add += n
            destroy += n
    return add, change, destroy


def next_number(root: Path) -> int:
    nums = [int(m.group(1)) for p in (root / ADR_DIR).glob("*.md") if (m := re.match(r"(\d{4})-", p.name))]
    return max(nums, default=0) + 1


@dataclass
class Draft:
    sections: dict
    from_model: bool


def draft_sections(llm, request: str, units: list[dict], reasons: list[str]) -> Draft:
    brief = [{"env": u["env"], "unit": u["unit"], "module": u["module"],
              "inputs": {k: v for k, v in u["inputs"].items() if k != "tags"}} for u in units]
    defaults = {m: MODULE_DEFAULTS[m] for m in {u["module"] for u in units} if m in MODULE_DEFAULTS}
    msg = PROMPT.format(request=request, units=json.dumps(brief), reasons=json.dumps(reasons),
                        defaults=json.dumps(defaults))
    for _ in range(2):
        try:
            text = llm.complete([{"role": "user", "content": msg}], SCHEMA)
            data = json.loads(text)
            if all(k in data for k in SCHEMA["required"]) and data["options"]:
                return Draft(data, True)
        except Exception:
            pass
    return Draft({"context": FALLBACK, "options": [], "chosen": "", "rationale": FALLBACK, "consequences": []}, False)


def render(number: int, title: str, request: str, labels: list[str], units: list[dict],
           plans: dict[str, dict], policies: dict[str, dict], diagram_name: str, draft: Draft,
           date: str | None = None) -> str:
    date = date or dt.date.today().isoformat()
    s = draft.sections
    out = [f"# {number:04d}. {title}", "",
           "- Status: Proposed",
           f"- Date: {date}",
           "- Deciders: _(the reviewer: name yourself, then set Status to Accepted or Rejected)_",
           f"- Request: \"{' '.join(request.split())}\"" + (f" (labels: {', '.join(labels)})" if labels else ""),
           "", "## Context and problem statement", "", s["context"], "",
           "## Considered options", ""]
    out += [f"- **{o['name']}**: {o['summary']}" for o in s["options"]] or [FALLBACK]
    out += ["", "## Decision outcome", ""]
    out += [f"Chosen option: **{s['chosen']}**. {s['rationale']}" if s["chosen"] else FALLBACK, ""]
    if s["consequences"]:
        out += ["### Consequences", ""] + [f"- {c}" for c in s["consequences"]] + [""]
    out += [f"_The sections above were drafted by {'the model' if draft.from_model else 'nobody'}; "
            "check them. The section below is generated from the plan by code._", "",
            FACTS_HEADER, "", f"![Plan diagram]({diagram_name})", "",
            "| Unit | Env | Module | Add | Change | Destroy |", "|---|---|---|---|---|---|"]
    for u in units:
        a, c, d = counts(plans.get(f"{u['env']}-{u['unit']}", {}).get("actions", {}))
        out.append(f"| {u['unit']} | {u['env']} | {u['module']} | {a} | {c} | {d} |")
    passed = sum(1 for f in policies.values() if not f["fail"])
    rules = max((f["pass"] + f["fail"] for f in policies.values()), default=0)
    out += ["", f"Policies: {passed} of {len(policies)} plan files pass all {rules} Kyverno policies "
                "(scripts/check-policies.sh, against a local AWS mock). Nothing was applied.", ""]
    return "\n".join(out)


def parse_facts(md: str) -> dict:
    """Read the facts back: {"status", "units": {unit: (env, module, add, change, destroy)}}."""
    status = re.search(r"^- Status:\s*(\w+)", md, re.M)
    facts = md.split(FACTS_HEADER, 1)[1] if FACTS_HEADER in md else ""
    units = {}
    for m in re.finditer(r"^\| ([a-z0-9-]+) \| (\w+) \| ([a-z0-9-]+) \| (\d+) \| (\d+) \| (\d+) \|$", facts, re.M):
        units[m.group(1)] = (m.group(2), m.group(3), int(m.group(4)), int(m.group(5)), int(m.group(6)))
    return {"status": status.group(1) if status else None, "units": units}
