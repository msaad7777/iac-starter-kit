#!/usr/bin/env bash
# Prove every plan policy still fails on the deliberately non-compliant config.
# Needs a Moto server (source scripts/moto-env.sh) because terraform plan calls the AWS API.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/policies/terraform/tests/noncompliant"
cd "$DIR"
terraform init -input=false >/dev/null
terraform plan -input=false -lock=false -out=tfplan >/dev/null
terraform show -json tfplan > plan.json
rm -f tfplan
out=$(kyverno apply "$ROOT"/policies/terraform/*.yaml --json plan.json 2>&1 || true)
echo "$out" | grep -E "^[0-9]+ - |^pass:"
status=0
for f in "$ROOT"/policies/terraform/*.yaml; do
  name=$(basename "$f" .yaml)
  if echo "$out" | grep -q "policy $name -> resource JSON payload failed"; then
    echo "ok   $name catches its violation"
  else
    echo "FAIL $name did not fire on the non-compliant plan"; status=1
  fi
done
exit $status
