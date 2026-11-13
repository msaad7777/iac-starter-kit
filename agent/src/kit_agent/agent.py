"""The provisioning agent: a plain-English request in, Terragrunt units plus a PR body out.

The model plans and writes; the code holds the rules. It can only reach the tools below,
every write goes through Workspace (live/ only, kit modules only), and finish is refused
until the latest plan and policy run passed with nothing written since."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from . import catalog, config
from .gates import Gates, PlanResult, PolicyResult
from .llm import BadToolCall
from .workspace import Refused, ToolError, Workspace

SYSTEM = f"""You are kit-agent. You turn one infrastructure request into Terragrunt units that compose the kit's existing Terraform modules, then prove they pass the kit's gates. A human reviews and merges; you never apply.

Rules:
- Use only the modules list_modules shows. If the request needs any other kind of resource (database, cluster, function, queue, DNS...), call refuse.
- Buckets are always private; the module blocks public access. If the request asks for public or public-read access, call refuse.
- Every request needs a monthly budget in USD written in the request. Add one budget unit with exactly that amount. If no amount is written, call refuse. Never invent a number.
- Environments are dev, staging and prod. prod needs the label {config.PROD_APPROVAL_LABEL}; without it, call refuse.
- network: if the request gives no cidr or azs, use cidr 10.<n>.0.0/16 with an n no other env uses, and azs us-east-1a, us-east-1b, ... (as many as asked, else 2). A value the kit can default is never a reason to refuse; refuse only for the reasons above and below.
- Policies: outside prod at most one NAT gateway (nat_strategy single or none); GPU groups at most 50 percent on-demand above base; dev GPU groups need office_hours_schedule. If the request explicitly asks for something that breaks a policy, call refuse. Otherwise pick compliant settings.
- If the env does not exist yet, call create_env first (owner <team>-team, cost_center CC-1234 unless the request gives one).
- Unit names <team>-<purpose> (e.g. payments-bucket, payments-budget). Bucket names acme-<env>-<team>-<purpose>, lowercase. Budget name acme-<env>-<team>, alert_emails ["finops@example.com"] unless the request gives one.
- Set only the required variables and what the request asks for; leave every other variable unset so the module default applies. Never invent ARNs or IDs. For gpu-inference use ami_id "ami-0123456789abcdef0" (the kit's placeholder).
- tags input on every unit: {{"service": "<team>", "data-classification": "internal" or "confidential", "owner": "<team>-team"}}.

Steps: list_modules; create_env if needed; write_unit for each unit; run_plan; run_policies; if either fails, fix the units and run both again (you have {config.MAX_ATTEMPTS} plan runs); then finish with a title and one short reason per choice."""

TOOLS = [
    {"type": "function", "function": {
        "name": "list_modules", "description": "Kit modules, their variables (* = required) and existing environments.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "create_env", "description": "Create a new environment under live/.",
        "parameters": {"type": "object", "required": ["env", "owner", "cost_center"], "properties": {
            "env": {"type": "string", "enum": list(config.ENVIRONMENTS)},
            "owner": {"type": "string"}, "cost_center": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "write_unit", "description": "Write or overwrite one Terragrunt unit that uses one kit module.",
        "parameters": {"type": "object", "required": ["env", "unit", "module", "inputs"], "properties": {
            "env": {"type": "string", "enum": list(config.ENVIRONMENTS)},
            "unit": {"type": "string"}, "module": {"type": "string"},
            "inputs": {"type": "object", "description": "module variables"},
            "network_unit": {"type": "string", "description": "gpu-inference only"}}}}},
    {"type": "function", "function": {
        "name": "delete_unit", "description": "Delete a unit this run wrote.",
        "parameters": {"type": "object", "required": ["env", "unit"], "properties": {
            "env": {"type": "string"}, "unit": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "read_unit", "description": "Read a unit file.",
        "parameters": {"type": "object", "required": ["env", "unit"], "properties": {
            "env": {"type": "string"}, "unit": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "run_plan", "description": "terragrunt plan (local AWS mock) for the envs you changed. One attempt.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_policies", "description": "Kyverno policies on the plan JSON.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "finish", "description": "Done after plan and policies passed: PR title and one short reason per choice.",
        "parameters": {"type": "object", "required": ["title", "reasons"], "properties": {
            "title": {"type": "string"}, "reasons": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {
        "name": "refuse", "description": "Stop: the request breaks a rule or needs something the kit lacks.",
        "parameters": {"type": "object", "required": ["reason"], "properties": {"reason": {"type": "string"}}}}},
]

AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:usd|dollars)\b", re.I)


TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def text_tool_call(content: str) -> list[dict]:
    """gpt-oss sometimes writes a tool call as JSON in its reply instead of calling the tool.
    Accept it only when the whole reply is one JSON object naming a known tool."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (content or "").strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, dict) and obj.get("name") in TOOL_NAMES and isinstance(obj.get("arguments", {}), dict):
        return [{"function": {"name": obj["name"], "arguments": obj.get("arguments", {})}}]
    return []


def stated_amounts(request: str) -> set[float]:
    return {float((a or b).replace(",", "")) for a, b in AMOUNT.findall(request)}


@dataclass
class Result:
    outcome: str                       # "pr" | "refused" | "failed"
    reason: str = ""
    refused_by: str = ""               # "model" | "guard"
    title: str = ""
    reasons: list[str] = field(default_factory=list)
    attempts: int = 0
    llm_calls: int = 0
    seconds: float = 0.0
    units: list[dict] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)   # one row per gate run
    plans: dict = field(default_factory=dict)
    policies: dict = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)
    text_tool_calls: int = 0           # tool calls the model wrote as JSON text instead
    bad_tool_calls: int = 0            # tool calls Ollama could not parse; sent back to the model
    adr: str = ""                      # docs/adr/NNNN-<slug>.md on the branch
    diagram: str = ""                  # docs/adr/NNNN-<slug>.png on the branch
    diagram_stats: dict = field(default_factory=dict)
    adr_from_model: bool = False
    max_prompt_tokens: int = 0         # largest prompt sent; near num_ctx means truncation risk


class Agent:
    def __init__(self, llm, gates: Gates, max_attempts: int = config.MAX_ATTEMPTS,
                 max_turns: int = config.MAX_TURNS, char_budget: int | None = None):
        self.llm, self.gates = llm, gates
        self.max_attempts, self.max_turns = max_attempts, max_turns
        # About 3.5 characters per token; the tool schemas and room for the reply come off the top.
        self.char_budget = char_budget or int(config.NUM_CTX * 3.5) - len(json.dumps(TOOLS)) - 3000

    # ---- tool dispatch -------------------------------------------------------------------
    def _tool(self, ws: Workspace, st: dict, name: str, args: dict) -> dict:
        if name == "list_modules":
            envs = ", ".join(f"{e} ({'exists' if ok else 'new: create_env first'})" for e, ok in ws.envs().items())
            return {"ok": True, "modules": catalog.describe(ws.modules), "environments": envs}
        if name == "create_env":
            return ws.create_env(**args)
        if name == "write_unit":
            inputs = args.get("inputs") or {}
            if isinstance(inputs, str):
                try:
                    inputs = json.loads(inputs)
                except json.JSONDecodeError as e:
                    raise ToolError(f"inputs is not valid JSON: {e}")
            return ws.write_unit(args.get("env"), args.get("unit"), args.get("module"), inputs,
                                 args.get("network_unit") or None)
        if name == "delete_unit":
            return ws.delete_unit(**args)
        if name == "read_unit":
            return ws.read_unit(**args)
        if name == "run_plan":
            if not ws.units():
                raise ToolError("write at least one unit first")
            if st["attempts"] >= self.max_attempts:
                st["end"] = Result("failed", reason=f"no passing plan after {self.max_attempts} attempts")
                return {"ok": False, "error": "out of attempts"}
            st["attempts"] += 1
            p: PlanResult = self.gates.plan(ws.root, ws.touched_envs())
            ws.dirty = False
            st["plan"], st["policy"] = p, None
            st["history"].append({"attempt": st["attempts"], "gate": "plan", "ok": p.ok,
                                  "detail": p.error[:600], "seconds": round(p.seconds, 1)})
            if not p.ok:
                return {"ok": False, "error": p.error}
            mine = {k: v for k, v in p.plans.items() if self._is_mine(ws, k)}
            return {"ok": True, "plans": mine, "next": "run_policies"}
        if name == "run_policies":
            p = st.get("plan")
            if not p or not p.ok or ws.dirty:
                raise ToolError("run_plan must pass after your last change before run_policies")
            r: PolicyResult = self.gates.policies(ws.root)
            st["policy"] = r
            bad = {k: v["violations"] or [f"{v['fail']} failed"] for k, v in r.files.items()
                   if v["fail"] or v["violations"]}
            st["history"].append({"attempt": st["attempts"], "gate": "policies", "ok": r.ok,
                                  "detail": json.dumps(bad)[:600], "seconds": round(r.seconds, 1)})
            if r.ok:
                return {"ok": True, "checked": len(r.files), "next": "finish"}
            return {"ok": False, "violations": bad or "policy check failed"}
        if name == "finish":
            return self._finish(ws, st, args)
        if name == "refuse":
            st["end"] = Result("refused", reason=str(args.get("reason", ""))[:500], refused_by="model")
            return {"ok": True}
        raise ToolError(f"no tool named {name}")

    @staticmethod
    def _is_mine(ws: Workspace, plan_name: str) -> bool:
        return any(plan_name == f"{u['env']}-{u['unit']}" for u in ws.units())

    def _finish(self, ws: Workspace, st: dict, args: dict) -> dict:
        p, r = st.get("plan"), st.get("policy")
        if ws.dirty or not (p and p.ok and r and r.ok):
            raise ToolError("finish needs run_plan and run_policies to pass after your last change")
        amounts = stated_amounts(ws.request)
        if not amounts:
            raise Refused("the request states no monthly budget in USD")
        budgets = [u for u in ws.units() if u["module"] == "budget"]
        if not budgets:
            raise ToolError("add a budget unit with the amount from the request")
        for b in budgets:
            if float(b["inputs"].get("monthly_limit_usd", -1)) not in amounts:
                raise ToolError(f"budget {b['unit']} must use an amount stated in the request: "
                                f"{', '.join(f'{a:g}' for a in sorted(amounts))}")
        reasons = args.get("reasons") or []
        if isinstance(reasons, (str, dict)):
            reasons = [reasons]
        # gpt-oss sometimes sends {"unit": ..., "reason": ...} objects instead of strings.
        reasons = [" — ".join(str(v) for v in r.values()) if isinstance(r, dict) else r for r in reasons]
        st["end"] = Result("pr", title=str(args.get("title", ""))[:120], reasons=[str(x)[:300] for x in reasons][:12])
        return {"ok": True}

    # ---- loop ----------------------------------------------------------------------------
    def _trim(self, messages: list[dict]) -> None:
        """Keep the prompt inside the context window: blank out the oldest tool results."""
        size = sum(len(json.dumps(m)) for m in messages)
        for m in messages[2:-4]:
            if size <= self.char_budget:
                break
            if m.get("role") == "tool" and m["content"] != "[older result trimmed]":
                size -= len(m["content"]) - 22
                m["content"] = "[older result trimmed]"

    @staticmethod
    def _nudge(ws: Workspace, st: dict) -> str:
        """What to say when the model replies in text. Once the gates have passed, a generic
        "call a tool or refuse" pushed gpt-oss into refusing valid work (eval run 1, pr-07)."""
        p, r = st.get("plan"), st.get("policy")
        if not ws.dirty and p and p.ok and r and r.ok:
            return (f"run_plan and run_policies passed. Call finish now with a PR title and one short "
                    f"reason per choice. Request: {ws.request}")
        return "Call a tool now. If you cannot do the request, call refuse with the reason."

    def run(self, ws: Workspace) -> Result:
        t0 = time.perf_counter()
        st = {"attempts": 0, "history": [], "plan": None, "policy": None, "end": None}
        labels = ", ".join(ws.labels) or "none"
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Request: {ws.request}\nLabels: {labels}"}]
        transcript = []
        prompt_tokens: list[int] = []
        nudges = text_calls = bad_calls = 0
        for _ in range(self.max_turns):
            self._trim(messages)
            try:
                msg = self.llm.chat(messages, TOOLS)
                prompt_tokens.append(getattr(self.llm, "last_prompt_tokens", 0))
            except BadToolCall as e:
                bad_calls += 1
                transcript.append({"say": f"(invalid tool call JSON) {e}"[:300]})
                if bad_calls > 2:
                    st["end"] = Result("failed", reason=f"invalid tool call JSON 3 times: {e}"[:300])
                    break
                messages.append({"role": "user", "content": "Your last tool call was not valid JSON and was "
                                 f"rejected: {str(e)[-300:]} Call the tool again with valid JSON arguments."})
                continue
            except Exception as e:  # network, timeout, bad JSON from the server
                st["end"] = Result("failed", reason=f"LLM error: {e}")
                break
            calls = msg.get("tool_calls") or []
            if not calls and (calls := text_tool_call(msg.get("content", ""))):
                text_calls += 1
            messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
            if not calls:
                nudges += 1
                transcript.append({"say": (msg.get("content") or "")[:300]})
                if nudges > 2:
                    st["end"] = Result("failed", reason="model stopped calling tools")
                    break
                messages.append({"role": "user", "content": self._nudge(ws, st)})
                continue
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                try:
                    out = self._tool(ws, st, name, args)
                except Refused as e:
                    st["end"] = Result("refused", reason=str(e), refused_by="guard")
                    out = {"ok": False, "refused": str(e)}
                except ToolError as e:
                    out = {"ok": False, "error": str(e)}
                except TypeError as e:
                    out = {"ok": False, "error": f"bad arguments for {name}: {e}"}
                transcript.append({"tool": name, "args": args, "result": out})
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(out)[:2500]})
                if st["end"]:
                    break
            if st["end"]:
                break
        res = st["end"] or Result("failed", reason=f"no finish after {self.max_turns} model turns")
        res.attempts = st["attempts"]
        res.llm_calls = getattr(self.llm, "calls", 0)
        res.seconds = round(time.perf_counter() - t0, 1)
        res.units = ws.units()
        res.files = sorted(ws.written)
        res.history = st["history"]
        res.transcript = transcript
        res.max_prompt_tokens = max(prompt_tokens, default=0)
        res.text_tool_calls = text_calls
        res.bad_tool_calls = bad_calls
        if st["plan"] and st["plan"].ok:
            res.plans = {k: v for k, v in st["plan"].plans.items() if self._is_mine(ws, k)}
        if st["policy"]:
            res.policies = st["policy"].files
        return res


def pr_body(request: str, labels: list[str], res: Result, model: str) -> str:
    out = ["## Request", "", f"> {' '.join(request.split())}", "",
           f"Labels: {', '.join(labels) or 'none'}", "", "## What this adds", "",
           "| Env | Unit | Module | Settings |", "|---|---|---|---|"]
    for u in res.units:
        settings = ", ".join(f"{k}={json.dumps(v)}" for k, v in u["inputs"].items() if k != "tags")
        if u.get("network_unit"):
            settings += f", subnets from {u['network_unit']}"
        out.append(f"| {u['env']} | `{u['unit']}` | `modules/{u['module']}` | {settings.replace('|', '/')} |")
    out += ["", "## Plan (terragrunt plan against a local AWS mock; nothing applied)", "",
            "| Plan | Actions | Resource types |", "|---|---|---|"]
    for name, s in res.plans.items():
        acts = ", ".join(f"{n} {a}" for a, n in s["actions"].items())
        types = ", ".join(f"{t} ×{n}" for t, n in s["types"].items())
        out.append(f"| {name} | {acts} | {types} |")
    out += ["", f"## Policy results ({len(res.policies)} plan files, scripts/check-policies.sh)", "",
            "| Plan | Pass | Fail |", "|---|---|---|"]
    for name, f in res.policies.items():
        out.append(f"| {name} | {f['pass']} | {f['fail']} |")
    if res.adr:
        st = res.diagram_stats
        out += ["", "## Decision record and diagram", "",
                f"- ADR draft: `{res.adr}`, status **Proposed**. Read it, fill in the deciders, set it to "
                "Accepted, then merge: CI fails while it is Proposed.",
                f"- Diagram drawn by code from the plan JSON: `{res.diagram}` "
                f"({st.get('drawn', 0)} resources with their own icon, {st.get('folded', 0)} shown on a parent, "
                f"{st.get('missed', 0)} missed)."]
    out += ["", "## Why these choices", ""] + [f"- {r}" for r in res.reasons]
    out += ["", f"## Attempts ({res.attempts} plan runs)", ""]
    for h in res.history:
        line = f"{h['attempt']}. {h['gate']}: {'passed' if h['ok'] else 'failed'} ({h['seconds']} s)"
        if not h["ok"] and h["detail"]:
            line += " — " + " ".join(h["detail"].split())[:240]
        out.append(line)
    out += ["", "## Before merging", "",
            "- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is "
            "added, it runs after merge against Moto or the AWS Emulator only.",
            "- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.",
            "", f"_Written by kit-agent ({model} via Ollama, {res.llm_calls} model calls, {res.seconds:.0f} s)._", ""]
    return "\n".join(out)
