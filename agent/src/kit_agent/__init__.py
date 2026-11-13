"""kit-agent: turn a plain-English request into Terragrunt units, gate them, and leave a branch."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import adr, config, plandiagram
from .agent import Agent, Result, pr_body
from .gates import Gates
from .gitops import Worktree, slug
from .llm import Ollama
from .workspace import Workspace


def record(llm, root: Path, request: str, labels: list[str], res: Result) -> None:
    """Fixed pipeline steps after the gates pass: diagram from the plan JSON, then the ADR draft."""
    full = plandiagram.from_plan_files(root / "plans", res.units)
    model = plandiagram.build(full, res.units)
    name = f"{adr.next_number(root):04d}-{slug(res.title or request)}"
    png = plandiagram.render(model, res.title or request[:80], root / adr.ADR_DIR / f"{name}.png")
    res.diagram = str(png.relative_to(root))
    res.diagram_stats = {"drawn": len(model.drawn), "folded": len(model.folded), "missed": len(model.missed),
                         "coverage": round(model.coverage(), 4), "missed_addresses": model.missed}
    draft = adr.draft_sections(llm, request, res.units, res.reasons)
    res.adr_from_model = draft.from_model
    md = adr.render(adr.next_number(root), res.title or request[:80], request, labels, res.units,
                    res.plans, res.policies, png.name, draft)
    res.adr = f"{adr.ADR_DIR}/{name}.md"
    (root / res.adr).write_text(md)


def provision(request: str, labels: list[str], llm=None, gates=None, repo: Path = config.KIT_ROOT,
              base: str = "HEAD", keep_branch: bool = True, out_dir: Path | None = None,
              prefix: str = config.BRANCH_PREFIX, max_attempts: int = config.MAX_ATTEMPTS) -> tuple[Result, str | None, str]:
    """Run one request in its own worktree. Returns (result, branch or None, PR body)."""
    llm = llm or Ollama()
    gates = gates or Gates()
    wt = Worktree(repo, request, base, prefix)
    branch, body = None, ""
    try:
        ws = Workspace(wt.path, request, labels)
        res = Agent(llm, gates, max_attempts=max_attempts).run(ws)
        model = getattr(llm, "model", "scripted")
        if res.outcome == "pr":
            record(llm, wt.path, request, labels, res)
            body = pr_body(request, labels, res, model)
            subject = res.title or f"agent: {request[:60]}"
            wt.commit(res.files + [res.adr, res.diagram], subject, body + "\nGenerated-by: kit-agent\n")
            branch = wt.branch
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(json.dumps(
                {"request": request, "labels": labels, "branch": branch, **asdict(res)}, indent=2, default=str))
            if body:
                (out_dir / "pr-body.md").write_text(body)
    finally:
        wt.close(keep_branch=keep_branch and branch is not None)
    return res, branch, body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kit-agent", description=__doc__)
    ap.add_argument("request", help='e.g. "a staging environment for team payments with a private bucket and a $200 budget"')
    ap.add_argument("--label", action="append", default=[], help=f"request labels, e.g. {config.PROD_APPROVAL_LABEL}")
    ap.add_argument("--base", default="HEAD", help="commit to branch from")
    ap.add_argument("--attempts", type=int, default=config.MAX_ATTEMPTS)
    args = ap.parse_args(argv)
    out = config.RUNS / slug(args.request)
    res, branch, body = provision(args.request, args.label, out_dir=out, max_attempts=args.attempts)
    print(f"outcome: {res.outcome}" + (f" ({res.refused_by}: {res.reason})" if res.reason else ""))
    print(f"attempts: {res.attempts}, model calls: {res.llm_calls}, {res.seconds} s")
    if branch:
        print(f"branch: {branch}  (not pushed; PR body in {out / 'pr-body.md'})")
    return 0 if res.outcome in ("pr", "refused") else 1


if __name__ == "__main__":
    sys.exit(main())
