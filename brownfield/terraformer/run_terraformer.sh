#!/usr/bin/env bash
# Legacy path: bulk-export existing resources with Terraformer.
# Terraformer's repository was archived in March 2026, so prefer ../discover (native import
# blocks). This script is kept for estates too large to list by hand.
set -euo pipefail
cd "$(dirname "$0")"
WORK="${WORK:-./out}"
mkdir -p "$WORK"
cp versions.tf "$WORK/"
cd "$WORK"
terraform init -input=false >/dev/null
terraformer import aws --resources="${RESOURCES:-s3,vpc,subnet,sg}" --regions="${AWS_REGION:-us-east-1}"

# Terraformer exits 0 even when every service fails, so check that it produced something.
if ! ls generated/aws/*/*.tf >/dev/null 2>&1; then
  echo "Terraformer generated no files; check the log above for errors." >&2
  exit 1
fi
echo "Generated $(grep -h '^resource' generated/aws/*/*.tf | wc -l | tr -d ' ') resources in $WORK/generated"
