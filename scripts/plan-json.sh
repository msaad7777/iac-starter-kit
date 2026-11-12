#!/usr/bin/env bash
# Write one Terraform plan JSON per Terragrunt unit, for the Kyverno policies to check.
#   scripts/plan-json.sh dev          -> plans/dev-<unit>.json
set -euo pipefail
ENV="${1:?usage: plan-json.sh <env>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/plans"
mkdir -p "$OUT"
for unit in "$ROOT"/live/"$ENV"/*/*/; do
  name="$ENV-$(basename "$unit")"
  (
    cd "$unit"
    terragrunt plan --non-interactive -input=false -lock=false -out=tfplan >/dev/null
    terragrunt show --non-interactive -json tfplan > "$OUT/$name.json"
    rm -f tfplan
  )
  echo "plans/$name.json"
done
