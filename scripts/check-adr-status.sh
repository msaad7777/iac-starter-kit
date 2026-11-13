#!/usr/bin/env bash
# Fail while any ADR this branch adds or changes is still "Proposed".
# The agent drafts every ADR as Proposed; a person reads it, names the deciders, sets the
# status to Accepted (or Rejected), and only then can the pull request pass.
#   scripts/check-adr-status.sh [base-ref]      default: origin/main
set -euo pipefail
BASE="${1:-origin/main}"
cd "$(cd "$(dirname "$0")/.." && pwd)"
status=0
checked=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  checked=$((checked + 1))
  if grep -Eiq '^[-*]?[[:space:]]*status:[[:space:]]*\**proposed' "$f"; then
    echo "FAIL $f is still Proposed: review it and set Status to Accepted or Rejected"
    status=1
  else
    echo "ok   $f"
  fi
done < <(git diff --name-only --diff-filter=AM "$BASE"...HEAD -- 'docs/adr/*.md')
echo "$checked ADR(s) changed on this branch"
exit $status
