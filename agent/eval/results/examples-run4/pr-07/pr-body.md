## Request

> Staging bucket for team mobile's release artifacts, $80/month budget.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| staging | `mobile-release-artifacts` | `modules/s3-bucket` | name="acme-staging-mobile-release-artifacts" |
| staging | `mobile` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=80, name="acme-staging-mobile" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| staging-mobile-release-artifacts | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |
| staging-mobile | 1 create | aws_budgets_budget ×1 |

## Policy results (2 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| staging-mobile-release-artifacts.json | 5 | 0 |
| staging-mobile.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-staging-bucket-and-budget-for-mobile-rel.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-staging-bucket-and-budget-for-mobile-rel.png` (2 resources with their own icon, 6 shown on a parent, 0 missed).

## Why these choices

- private bucket with default settings — Bucket
- 80 USD monthly limit — Budget

## Attempts (1 plan runs)

1. plan: passed (29.9 s)
1. policies: passed (0.6 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 8 model calls, 202 s)._
