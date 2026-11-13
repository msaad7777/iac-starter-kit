## Request

> Team analytics needs a dev bucket for raw logs that keeps old versions for 30 days, and a $120 budget.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| dev | `analytics-raw-logs` | `modules/s3-bucket` | name="acme-dev-analytics-raw-logs", noncurrent_version_expiration_days=30, versioning=true |
| dev | `analytics-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=120, name="acme-dev-analytics" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| dev-analytics-budget | 1 create | aws_budgets_budget ×1 |
| dev-analytics-raw-logs | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |

## Policy results (6 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| dev-analytics-budget.json | 5 | 0 |
| dev-analytics-raw-logs.json | 5 | 0 |
| dev-assets-bucket.json | 5 | 0 |
| dev-budget.json | 5 | 0 |
| dev-llm-inference.json | 5 | 0 |
| dev-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-add-analytics-dev-bucket-and-budget.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-add-analytics-dev-bucket-and-budget.png` (2 resources with their own icon, 6 shown on a parent, 0 missed).

## Why these choices

- Bucket with versioning and 30‑day retention — analytics-raw-logs
- 120 USD monthly budget — analytics-budget

## Attempts (1 plan runs)

1. plan: passed (97.1 s)
1. policies: passed (1.7 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 7 model calls, 252 s)._
