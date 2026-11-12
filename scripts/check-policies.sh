#!/usr/bin/env bash
# Run every Kyverno plan policy against every plan JSON in plans/. Exits non-zero on any failure.
# Policy files are passed explicitly: `kyverno apply <dir>` silently loaded zero policies
# once the directory also held test fixtures.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POLICIES=("$ROOT"/policies/terraform/*.yaml)
status=0
for plan in "$ROOT"/plans/*.json; do
  echo "== $(basename "$plan")"
  out=$(kyverno apply "${POLICIES[@]}" --json "$plan" 2>&1)
  echo "$out" | grep -E "^pass:|^[0-9]+ - " || true
  summary=$(echo "$out" | grep -E "^pass:")
  pass=$(echo "$summary" | sed -E 's/pass: ([0-9]+).*/\1/')
  fail=$(echo "$summary" | sed -E 's/.*fail: ([0-9]+).*/\1/')
  if [ "${fail:-1}" != "0" ] || [ "${pass:-0}" != "${#POLICIES[@]}" ]; then status=1; fi
done
exit $status
