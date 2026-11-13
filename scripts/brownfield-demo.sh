#!/usr/bin/env bash
# End-to-end brownfield demo against a local Moto server (or, with KIT_TARGET=emulator,
# a freshly started AWS Emulator, which has no reset API):
#   1. seed a click-ops estate   2. discover it and plan the import   3. adopt the bucket into a module
# Asserts the exact plan summaries, so CI fails if any step drifts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${KIT_TARGET:-moto}" = "emulator" ]; then
  source "$ROOT/scripts/emulator-env.sh"
else
  source "$ROOT/scripts/moto-env.sh"
fi
PY="${PYTHON:-python3}"

expect() {  # expect <dir> <plan summary>
  local out
  out=$(cd "$1" && terraform plan -input=false -lock=false -no-color 2>&1 | grep -E "^Plan:|^No changes" || true)
  if [ "$out" = "$2" ]; then echo "ok   $1: $out"; else echo "FAIL $1: got '$out', expected '$2'"; exit 1; fi
}

if [ "$KIT_TARGET" = "moto" ]; then curl -sf -X POST "$MOTO_URL/moto-api/reset" >/dev/null; fi
$PY "$ROOT/brownfield/seed_clickops.py"

cd "$ROOT/brownfield/discover"
$PY discover.py --out imports.tf
terraform init -input=false >/dev/null
expect "$ROOT/brownfield/discover" "Plan: 4 to import, 0 to add, 0 to change, 0 to destroy."

cd "$ROOT/brownfield/adopt"
rm -f terraform.tfstate terraform.tfstate.backup
terraform init -input=false >/dev/null
expect "$ROOT/brownfield/adopt" "Plan: 1 to import, 6 to add, 1 to change, 0 to destroy."
