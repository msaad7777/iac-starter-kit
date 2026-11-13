## Request

> Prod bucket for team payments' invoices, with a $1000 budget.

Labels: prod-approved

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| prod | `payments-bucket` | `modules/s3-bucket` | name="acme-prod-payments-invoices" |
| prod | `payments-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=1000, name="acme-prod-payments" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| prod-payments-bucket | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |
| prod-payments-budget | 1 create | aws_budgets_budget ×1 |

## Policy results (6 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| prod-assets-bucket.json | 5 | 0 |
| prod-budget.json | 5 | 0 |
| prod-llm-inference.json | 5 | 0 |
| prod-network.json | 5 | 0 |
| prod-payments-bucket.json | 5 | 0 |
| prod-payments-budget.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-add-payments-bucket-and-budget.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-add-payments-bucket-and-budget.png` (2 resources with their own icon, 6 shown on a parent, 0 missed).

## Why these choices

- private bucket with default settings — $1000 monthly budget

## Attempts (1 plan runs)

1. plan: passed (96.1 s)
1. policies: passed (1.7 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 6 model calls, 223 s)._
