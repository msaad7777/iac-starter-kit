## Request

> Staging: team growth wants a bucket that moves objects to intelligent tiering after 60 days, and a $90 budget with alerts to growth-finops@example.com.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| staging | `growth-bucket` | `modules/s3-bucket` | intelligent_tiering_after_days=60, name="acme-staging-growth-bucket" |
| staging | `growth-budget` | `modules/budget` | actual_threshold_percent=80, alert_emails=["growth-finops@example.com"], forecast_threshold_percent=80, monthly_limit_usd=90, name="acme-staging-growth" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| staging-growth-bucket | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |
| staging-growth-budget | 1 create | aws_budgets_budget ×1 |

## Policy results (2 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| staging-growth-bucket.json | 5 | 0 |
| staging-growth-budget.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-staging-growth-bucket-and-budget.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-staging-growth-bucket-and-budget.png` (2 resources with their own icon, 6 shown on a parent, 0 missed).

## Why these choices

- intelligent_tiering_after_days set to 60 — s3-bucket
- 90 USD monthly limit with alerts — budget

## Attempts (1 plan runs)

1. plan: passed (30.0 s)
1. policies: passed (0.6 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 7 model calls, 179 s)._
