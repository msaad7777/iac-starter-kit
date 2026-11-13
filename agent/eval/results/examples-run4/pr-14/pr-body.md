## Request

> Dev bucket for team docs with versioning turned off, and a $40 budget.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| dev | `docs-bucket` | `modules/s3-bucket` | name="acme-dev-docs-bucket", versioning=false |
| dev | `docs-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=40, name="acme-dev-docs" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| dev-docs-bucket | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |
| dev-docs-budget | 1 create | aws_budgets_budget ×1 |

## Policy results (6 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| dev-assets-bucket.json | 5 | 0 |
| dev-budget.json | 5 | 0 |
| dev-docs-bucket.json | 5 | 0 |
| dev-docs-budget.json | 5 | 0 |
| dev-llm-inference.json | 5 | 0 |
| dev-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-create-dev-bucket-and-budget-for-docs-te.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-create-dev-bucket-and-budget-for-docs-te.png` (2 resources with their own icon, 6 shown on a parent, 0 missed).

## Why these choices

- Bucket is private by default and versioning disabled as requested — Bucket created with private default
- Monthly budget matches request — Budget set to $40

## Attempts (1 plan runs)

1. plan: passed (91.8 s)
1. policies: passed (1.4 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 6 model calls, 238 s)._
