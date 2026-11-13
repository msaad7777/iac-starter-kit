"""Draw docs/agent-architecture.svg (and .png) in the style of docs/architecture.png.

The numbers in the "Measured" row come from eval/results/results.json, so the picture cannot
drift from the eval.   uv run python eval/architecture_diagram.py"""
from __future__ import annotations

import json
import shutil
import subprocess
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
DOCS = HERE.parents[1] / "docs"
W, H = 1920, 1280
KIND = {  # stroke/header, card fill
    "input": ("#475569", "#f8fafc"), "code": ("#2563eb", "#eff6ff"), "model": ("#7c3aed", "#f5f3ff"),
    "data": ("#0d9488", "#f0fdfa"), "gate": ("#ea580c", "#fff7ed"),
}
out: list[str] = []


def text(x, y, s, size=22, weight=500, fill="#334155", anchor="middle"):
    out.append(f"<text x='{x}' y='{y}' font-size='{size}' font-weight='{weight}' fill='{fill}' "
               f"text-anchor='{anchor}'>{escape(s)}</text>")


def band(y, h, fill, pill, label, right=False):
    out.append(f"<rect x='50' y='{y}' width='1820' height='{h}' rx='22' fill='{fill}'/>")
    w = 26 + len(label) * 12
    x = 1846 - w if right else 74
    out.append(f"<rect x='{x}' y='{y + 18}' width='{w}' height='38' rx='19' fill='{pill}'/>")
    text(x + w / 2, y + 45, label, 22, 700, "#ffffff")


def card(x, y, w, h, kind, title, lines):
    stroke, fill = KIND[kind]
    out.append(f"<g filter='url(#sh)'><rect x='{x}' y='{y}' width='{w}' height='{h}' rx='16' fill='{fill}' "
               f"stroke='{stroke}' stroke-width='3'/></g>")
    out.append(f"<path d='M{x},{y + 16} a16,16 0 0 1 16,-16 h{w - 32} a16,16 0 0 1 16,16 v38 h-{w} z' fill='{stroke}'/>")
    text(x + w / 2, y + 38, title, 27, 800, "#ffffff")
    for i, ln in enumerate(lines):
        text(x + w / 2, y + 88 + 31 * i, ln)


def arrow(d, dashed=False):
    dash = " stroke-dasharray='10 8'" if dashed else ""
    out.append(f"<path d='{d}' stroke='#334155' stroke-width='3.5' fill='none'{dash} marker-end='url(#a)'/>")


def stat(x, value, label, color):
    y = 1100
    out.append(f"<rect x='{x}' y='{y}' width='345' height='120' rx='16' fill='#ffffff' stroke='{color}' stroke-width='3'/>")
    out.append(f"<rect x='{x}' y='{y}' width='12' height='120' rx='6' fill='{color}'/>")
    text(x + 179, y + 58, value, 40, 800, color)
    text(x + 179, y + 96, label, 20, 600)


def main(results: Path = HERE / "results" / "results.json", docs: Path = DOCS):
    s = json.loads(results.read_text())["summary"]
    out.append(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}' "
               "font-family=\"Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif\">")
    out.append("<defs><linearGradient id='band' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#4f46e5'/>"
               "<stop offset='0.55' stop-color='#9333ea'/><stop offset='1' stop-color='#db2777'/></linearGradient>"
               "<filter id='sh' x='-10%' y='-10%' width='120%' height='130%'><feDropShadow dx='0' dy='3' stdDeviation='4' "
               "flood-color='#0f172a' flood-opacity='0.12'/></filter><marker id='a' viewBox='0 0 10 10' refX='8' refY='5' "
               "markerWidth='7' markerHeight='7' orient='auto-start-reverse'><path d='M0,0 L10,5 L0,10 z' fill='#334155'/>"
               "</marker></defs>")
    out.append(f"<rect width='{W}' height='{H}' fill='#ffffff'/><rect x='0' y='0' width='{W}' height='150' fill='url(#band)'/>")
    text(50, 78, "iac-starter-kit: provisioning agent", 48, 800, "#ffffff", "start")
    text(50, 122, "A plain-English request becomes Terragrunt units, checked by the kit's own gates, on a branch a human reviews.",
         25, 500, "#f5f3ff", "start")
    text(1870, 122, "github.com/msaad7777/iac-starter-kit", 23, 600, "#fce7f3", "end")

    cw, gap, x0 = 392, 64, 80
    xs = [x0 + i * (cw + gap) for i in range(4)]
    # Band 1: request -> model -> tools -> guards
    band(190, 242, "#eef2ff", "#4338ca", "Agent (local, gpt-oss:20b)")
    card(xs[0], 260, cw, 138, "input", "Request", ['"staging for payments,', 'private bucket, $200 budget"'])
    card(xs[1], 260, cw, 138, "model", "gpt-oss:20b", ["tool calls through Ollama,", "no cloud model"])
    card(xs[2], 260, cw, 138, "code", "9 tools", ["modules, env, write/read/delete", "unit, plan, policies, finish, refuse"])
    card(xs[3], 260, cw, 138, "gate", "Rules in code", ["live/ only, kit modules only,", "prod label, stated budget"])
    for i in range(3):
        arrow(f"M{xs[i] + cw + 4},329 L{xs[i + 1] - 8},329")

    # Band 2: units -> plan -> kyverno -> branch
    band(462, 312, "#ecfeff", "#0e7490", "Kit gates, against Moto", right=True)
    card(xs[0], 560, cw, 138, "data", "live/<env>/ units", ["Terragrunt, one per", "module; nothing else"])
    card(xs[1], 560, cw, 138, "code", "plan-json.sh", ["terragrunt plan", "to JSON, no apply"])
    card(xs[2], 560, cw, 138, "gate", "check-policies.sh", ["5 Kyverno policies:", "tags, S3, IMDSv2, GPU, NAT"])
    card(xs[3], 560, cw, 138, "data", "Diagram, ADR, branch", ["icons drawn from plan JSON,", "ADR Proposed, PR body"])
    arrow(f"M{xs[3] + cw / 2},398 L{xs[3] + cw / 2},447 L{xs[0] + cw / 2},447 L{xs[0] + cw / 2},552")
    for i in range(3):
        arrow(f"M{xs[i] + cw + 4},629 L{xs[i + 1] - 8},629")
    # failure loop back to the model
    arrow(f"M{xs[2] + cw / 2},698 L{xs[2] + cw / 2},720 L{xs[1] - 30},720 L{xs[1] - 30},346 L{xs[1] - 8},346", dashed=True)
    text(xs[1] + 10, 756, f"fail: model fixes its units, up to {s['max_attempts']} plan runs", 20, 600, "#c2410c", "start")

    # Band 3: humans and CI
    band(804, 242, "#fdf4ff", "#a21caf", "People and CI")
    card(xs[0], 874, cw, 138, "input", "Review and accept", ["a person opens the PR, edits", "the ADR to Accepted, merges"])
    card(xs[1], 874, cw, 138, "gate", "CI on the PR", ["plan, policies, Trivy; fails", "while the ADR is Proposed"])
    card(xs[2], 874, cw, 138, "code", "Any apply", ["not wired in CI yet; only after", "merge, Moto or AWS Emulator"])
    card(xs[3], 874, cw, 138, "input", "Never", ["agent apply, real AWS,", "push or opening the PR"])
    arrow(f"M{xs[3] + cw / 2},698 L{xs[3] + cw / 2},789 L{xs[0] + cw / 2},789 L{xs[0] + cw / 2},866")
    for i in range(2):
        arrow(f"M{xs[i] + cw + 4},943 L{xs[i + 1] - 8},943")

    text(50, 1080, "Measured", 30, 800, "#0f172a", "start")
    text(205, 1078, f"{s['requests']} requests: {s['should_pr']} valid, {s['should_refuse']} that must be refused; "
         f"gpt-oss:20b at num_ctx {s['num_ctx']}, Moto.", 22, 500, "#334155", "start")
    sx = [50 + i * 368.75 for i in range(5)]
    stat(sx[0], f"{s['pr_branches_passing_every_gate']} / {s['should_pr']}", "valid → branch passing gates", "#4f46e5")
    stat(sx[1], f"{s['refusals_correct']} / {s['should_refuse']}", "bad requests refused", "#9333ea")
    stat(sx[2], str(s["policy_violations_in_branches"]), "policy violations in a branch", "#db2777")
    stat(sx[3], f"{s['diagram_resources_shown']} / {s['diagram_resources_planned']}",
         f"on diagrams; {s['adr_fact_mismatches']} ADR fact errors", "#ea580c")
    stat(sx[4], f"{s['seconds_median']:.0f} s", "median time per request", "#0d9488")
    lx = 50
    for name, kind in (("Input", "input"), ("Code", "code"), ("Model", "model"), ("Data / output", "data"), ("Check / gate", "gate")):
        out.append(f"<rect x='{lx}' y='{H - 42}' width='22' height='22' rx='5' fill='{KIND[kind][0]}'/>")
        text(lx + 32, H - 24, name, 20, 600, anchor="start")
        lx += 50 + len(name) * 11
    text(1870, H - 24, "Ollama · Terragrunt · Kyverno · Moto · diagrams + Graphviz · git worktrees", 20, 600, anchor="end")
    out.append("</svg>")
    svg = docs / "agent-architecture.svg"
    svg.write_text("\n".join(out))
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(chrome).exists() or shutil.which("google-chrome"):
        exe = chrome if Path(chrome).exists() else shutil.which("google-chrome")
        subprocess.run([exe, "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
                        "--force-device-scale-factor=2", f"--screenshot={docs / 'agent-architecture.png'}",
                        svg.as_uri()], capture_output=True, timeout=120)
    print(svg)


if __name__ == "__main__":
    import sys
    main(*(Path(a) for a in sys.argv[1:3]))
