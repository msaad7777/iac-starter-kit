"""kit-assistant: ask the IaC starter kit (fetch | ingest | ask | serve)."""
from __future__ import annotations

import argparse
import json
import textwrap


def main() -> None:
    p = argparse.ArgumentParser(prog="kit-assistant", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download the external docs at a pinned commit")
    f.add_argument("--pinned", action="store_true", help="reuse the commit SHAs in data/manifest.json")
    sub.add_parser("ingest", help="chunk and index the kit and the fetched docs")
    a = sub.add_parser("ask", help="ask a question")
    a.add_argument("question")
    a.add_argument("--json", action="store_true")
    s = sub.add_parser("serve", help="run the HTTP API on 127.0.0.1")
    s.add_argument("--port", type=int, default=8010)
    args = p.parse_args()

    if args.cmd == "fetch":
        from .fetch import fetch
        fetch(pinned=args.pinned)
    elif args.cmd == "ingest":
        from .ingest import ingest
        print(f"indexed {ingest()} chunks")
    elif args.cmd == "ask":
        from .pipeline import RAG
        ans = RAG().ask(args.question)
        if args.json:
            print(json.dumps(ans.to_dict(), indent=2))
            return
        print(textwrap.fill(ans.answer, 100))
        for c in ans.citations:
            sec = f" > {c['section']}" if c["section"] else ""
            print(f"  [{c['n']}] {c['source']}: {c['path']}{sec}\n      {c['url']}")
        if ans.declined:
            print(f"  (declined: {ans.decline_reason})")
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("kit_assistant.api:app", host="127.0.0.1", port=args.port)
