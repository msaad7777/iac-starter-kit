## Request

> A dev environment for team support: a network with no NAT gateway, a private bucket, and a $60 budget.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| dev | `support-network` | `modules/network` | azs=["us-east-1a", "us-east-1b"], cidr="10.1.0.0/16", name="support", nat_strategy="none" |
| dev | `support-bucket` | `modules/s3-bucket` | name="support-bucket" |
| dev | `support-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=60, name="support" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| dev-support-bucket | 1 read, 7 create | aws_s3_bucket ×1, aws_s3_bucket_lifecycle_configuration ×1, aws_s3_bucket_ownership_controls ×1, aws_s3_bucket_policy ×1, aws_s3_bucket_public_access_block ×1, aws_s3_bucket_server_side_encryption_configuration ×1, aws_s3_bucket_versioning ×1 |
| dev-support-budget | 1 create | aws_budgets_budget ×1 |
| dev-support-network | 16 create | aws_internet_gateway ×1, aws_route ×1, aws_route_table ×3, aws_route_table_association ×4, aws_subnet ×4, aws_vpc ×1, aws_vpc_endpoint ×2 |

## Policy results (7 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| dev-assets-bucket.json | 5 | 0 |
| dev-budget.json | 5 | 0 |
| dev-llm-inference.json | 5 | 0 |
| dev-network.json | 5 | 0 |
| dev-support-bucket.json | 5 | 0 |
| dev-support-budget.json | 5 | 0 |
| dev-support-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-add-support-dev-environment.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-add-support-dev-environment.png` (13 resources with their own icon, 11 shown on a parent, 0 missed).

## Why these choices

- private VPC with no NAT gateway — support-network
- private bucket — support-bucket
- $60 monthly budget — support-budget

## Attempts (1 plan runs)

1. plan: passed (108.2 s)
1. policies: passed (1.9 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 7 model calls, 257 s)._
