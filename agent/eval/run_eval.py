"""Run every request in requests.jsonl through the real agent (gpt-oss:20b via Ollama) and the
real gates (Terragrunt plan against Moto, Kyverno), then re-check every branch it leaves.

    uv run python eval/run_eval.py                  # all requests
    uv run python eval/run_eval.py --only pr-01     # one request
    uv run python eval/run_eval.py --keep-branches  # keep the agent's branches afterwards

The re-check is independent of the agent: a fresh worktree of the committed branch, a fresh
plan of every environment it touched, and the kit's policy script. A violation that survives
to a branch is counted there."""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

from kit_agent import adr, config, plandiagram, provision
from kit_agent.gates import Gates, summarise_plan
from kit_agent.gitops import git
from kit_agent.llm import Ollama

HERE = Path(__file__).parent
OUT = HERE / "results"


def verify(branch: str, res, gates: Gates) -> dict:
    """Fresh worktree of the branch -> plan-json.sh -> check-policies.sh, then check the
    diagram and the ADR the pipeline committed against that fresh plan."""
    import tempfile
    envs = sorted({u["env"] for u in res.units})
    path = Path(tempfile.mkdtemp(prefix="kit-verify-")) / "kit"
    git(config.KIT_ROOT, "worktree", "add", "-q", "--detach", str(path), branch)
    try:
        p = gates.plan(path, envs)
        if not p.ok:
            return {"plan_ok": False, "policy_ok": False, "violations": 0, "error": p.error[:400]}
        r = gates.policies(path)
        out = {"plan_ok": True, "policy_ok": r.ok, "plans_checked": len(r.files),
               "violations": sum(f["fail"] for f in r.files.values()),
               "failing": {k: v["violations"] for k, v in r.files.items() if v["fail"]}}
        # Diagram coverage: every managed resource in the fresh plan of the agent's units must
        # have been drawn, either with its own icon or on its parent's node.
        fresh = plandiagram.from_plan_files(path / "plans", res.units)
        planned = {f"{name}/{rc['address']}" for name, plan in fresh.items()
                   for rc in plan.get("resource_changes", []) if rc.get("mode") == "managed"}
        model = plandiagram.build(fresh, res.units)
        shown = set(model.drawn) | set(model.folded)
        out["diagram"] = {"planned": len(planned), "shown": len(planned & shown),
                          "missed": sorted(planned - shown), "png_committed": (path / res.diagram).is_file()}
        # ADR facts: the committed table must match the fresh plan, unit by unit.
        facts = adr.parse_facts((path / res.adr).read_text()) if (path / res.adr).is_file() else {"status": None, "units": {}}
        mism = []
        for u in res.units:
            name = f"{u['env']}-{u['unit']}"
            want = (u["env"], u["module"], *adr.counts(summarise_plan(path / "plans" / f"{name}.json")["actions"]))
            got = facts["units"].get(u["unit"])
            if got != want:
                mism.append({"unit": u["unit"], "adr": got, "plan": want})
        extra = set(facts["units"]) - {u["unit"] for u in res.units}
        mism += [{"unit": x, "adr": facts["units"][x], "plan": None} for x in sorted(extra)]
        out["adr"] = {"status": facts["status"], "mismatches": mism}
        return out
    finally:
        subprocess.run(["git", "-C", str(config.KIT_ROOT), "worktree", "remove", "--force", str(path)], capture_output=True)


def composition(item: dict, res) -> dict:
    """For requests that should become a PR: right env, the modules asked for, the stated budget."""
    if item["expect"] != "pr" or res.outcome != "pr":
        return {}
    envs = {u["env"] for u in res.units}
    mods = {u["module"] for u in res.units}
    # Reusing the environment's existing network unit for a GPU group is a valid composition.
    for u in res.units:
        if u.get("network_unit") and (config.KIT_ROOT / "live" / u["env"] / config.REGION / u["network_unit"]).is_dir():
            mods.add("network")
    budgets = [u["inputs"].get("monthly_limit_usd") for u in res.units if u["module"] == "budget"]
    checks = {"env": envs == {item["env"]}, "modules": set(item["modules"]) <= mods,
              "budget": budgets == [item["budget"]]}
    return {"ok": all(checks.values()), **checks, "got_modules": sorted(mods), "got_envs": sorted(envs)}


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def summarise(rows: list[dict]) -> dict:
    want_pr = [r for r in rows if r["expect"] == "pr"]
    want_ref = [r for r in rows if r["expect"] == "refuse"]
    prs = [r for r in rows if r["outcome"] == "pr"]
    verified = [r for r in prs if r["verify"].get("policy_ok")]
    return {
        "requests": len(rows),
        "should_pr": len(want_pr), "should_refuse": len(want_ref),
        "pr_branches_passing_every_gate": len([r for r in want_pr if r["outcome"] == "pr" and r["verify"].get("policy_ok")]),
        "pr_branch_share_of_valid_requests": round(len([r for r in want_pr if r["outcome"] == "pr" and r["verify"].get("policy_ok")]) / max(1, len(want_pr)), 3),
        "composition_correct": len([r for r in want_pr if r["composition"].get("ok")]),
        "valid_requests_refused": len([r for r in want_pr if r["outcome"] == "refused"]),
        "valid_requests_failed": len([r for r in want_pr if r["outcome"] == "failed"]),
        "refusals_correct": len([r for r in want_ref if r["outcome"] == "refused"]),
        "refusals_by_guard": len([r for r in want_ref if r["outcome"] == "refused" and r["refused_by"] == "guard"]),
        "bad_requests_that_became_prs": len([r for r in want_ref if r["outcome"] == "pr"]),
        "bad_requests_failed_without_pr": len([r for r in want_ref if r["outcome"] == "failed"]),
        "policy_violations_in_branches": sum(r["verify"].get("violations", 0) for r in prs),
        "branches_failing_recheck": len(prs) - len(verified),
        "attempts_mean_all": round(statistics.mean(r["attempts"] for r in rows), 2),
        "attempts_mean_pr": round(statistics.mean(r["attempts"] for r in prs), 2) if prs else None,
        "attempts_max": max(r["attempts"] for r in rows),
        "first_attempt_pass_pr": len([r for r in prs if r["attempts"] == 1]),
        "seconds_median": pct([r["seconds"] for r in rows], 0.5),
        "seconds_p90": pct([r["seconds"] for r in rows], 0.9),
        "seconds_median_pr": pct([r["seconds"] for r in prs], 0.5),
        "seconds_median_refused": pct([r["seconds"] for r in rows if r["outcome"] == "refused"], 0.5),
        "llm_calls_mean": round(statistics.mean(r["llm_calls"] for r in rows), 1),
        "max_prompt_tokens": max(r["max_prompt_tokens"] for r in rows),
        "requests_with_text_tool_calls": len([r for r in rows if r["text_tool_calls"]]),
        "requests_with_bad_tool_calls": len([r for r in rows if r.get("bad_tool_calls")]),
        "diagram_resources_planned": sum(r["verify"].get("diagram", {}).get("planned", 0) for r in prs),
        "diagram_resources_shown": sum(r["verify"].get("diagram", {}).get("shown", 0) for r in prs),
        "diagram_misses": [m for r in prs for m in r["verify"].get("diagram", {}).get("missed", [])],
        "adr_fact_mismatches": sum(len(r["verify"].get("adr", {}).get("mismatches", [])) for r in prs),
        "adrs_proposed": len([r for r in prs if r["verify"].get("adr", {}).get("status") == "Proposed"]),
        "adr_sections_from_model": len([r for r in prs if r["adr_from_model"]]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--keep-branches", action="store_true")
    ap.add_argument("--base", default="main")
    ap.add_argument("--tag", default="results")
    args = ap.parse_args()
    items = [json.loads(l) for l in (HERE / "requests.jsonl").read_text().splitlines() if l.strip()]
    if args.only:
        items = [i for i in items if i["id"] in args.only]
    OUT.mkdir(exist_ok=True)
    gates = Gates()
    rows = []
    t_start = time.time()
    for n, item in enumerate(items, 1):
        llm = Ollama()
        res, branch, body = provision(item["request"], item["labels"], llm=llm, gates=gates, base=args.base,
                                      keep_branch=True, prefix="agent-eval/")
        check = verify(branch, res, gates) if branch else {}
        if branch:   # keep what a reviewer would see, before the branch goes
            ex = OUT / "examples" / item["id"]
            ex.mkdir(parents=True, exist_ok=True)
            (ex / "pr-body.md").write_text(body)
            for f in (res.adr, res.diagram):
                data = subprocess.run(["git", "-C", str(config.KIT_ROOT), "show", f"{branch}:{f}"],
                                      capture_output=True).stdout
                (ex / Path(f).name).write_bytes(data)
        if branch and not args.keep_branches:
            subprocess.run(["git", "-C", str(config.KIT_ROOT), "branch", "-D", branch], capture_output=True)
        row = {"id": item["id"], "expect": item["expect"], "why": item.get("why", ""), "request": item["request"],
               "labels": item["labels"], "outcome": res.outcome, "refused_by": res.refused_by,
               "reason": res.reason, "attempts": res.attempts, "llm_calls": res.llm_calls,
               "seconds": res.seconds, "max_prompt_tokens": res.max_prompt_tokens,
               "text_tool_calls": res.text_tool_calls, "bad_tool_calls": res.bad_tool_calls, "adr_from_model": res.adr_from_model,
               "diagram_stats": res.diagram_stats, "adr_file": res.adr,
               "branch": branch if args.keep_branches else None, "verify": check,
               "composition": composition(item, res), "units": res.units, "history": res.history,
               "reasons": res.reasons,
               "tools": [t.get("tool") or "(text)" for t in res.transcript],
               "said": [t["say"] for t in res.transcript if "say" in t]}
        rows.append(row)
        print(f"[{n}/{len(items)}] {item['id']} expect={item['expect']} -> {res.outcome}"
              f"{' (' + res.refused_by + ')' if res.refused_by else ''} attempts={res.attempts} "
              f"{res.seconds}s verify={check.get('policy_ok', '-')} comp={row['composition'].get('ok', '-')} "
              f"| {res.reason[:120]}", flush=True)
        (OUT / f"{args.tag}.json").write_text(json.dumps({"rows": rows}, indent=2, default=str))
    summary = summarise(rows)
    summary.update(model=config.LLM_MODEL, num_ctx=config.NUM_CTX, think=config.THINK,
                   max_attempts=config.MAX_ATTEMPTS, wall_clock_s=round(time.time() - t_start),
                   target="moto")
    (OUT / f"{args.tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
