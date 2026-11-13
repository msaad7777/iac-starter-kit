## Request

> Prod network for team platform with a NAT gateway in each of three AZs, budget $2500.

Labels: prod-approved

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| prod | `platform-network` | `modules/network` | azs=["us-east-1a", "us-east-1b", "us-east-1c"], cidr="10.1.0.0/16", name="platform", nat_strategy="per_az" |
| prod | `platform-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=2500, name="platform" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| prod-platform-budget | 1 create | aws_budgets_budget ×1 |
| prod-platform-network | 30 create | aws_eip ×3, aws_internet_gateway ×1, aws_nat_gateway ×3, aws_route ×4, aws_route_table ×4, aws_route_table_association ×6, aws_subnet ×6, aws_vpc ×1, aws_vpc_endpoint ×2 |

## Policy results (6 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| prod-assets-bucket.json | 5 | 0 |
| prod-budget.json | 5 | 0 |
| prod-llm-inference.json | 5 | 0 |
| prod-network.json | 5 | 0 |
| prod-platform-budget.json | 5 | 0 |
| prod-platform-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-add-production-network-with-per-az-nat-g.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-add-production-network-with-per-az-nat-g.png` (21 resources with their own icon, 10 shown on a parent, 0 missed).

## Why these choices

- network unit — Created platform-network with CIDR 10.1.0.0/16, three AZs, and per‑AZ NAT strategy
- budget unit — Created platform-budget with $2,500 monthly limit and default alert email

## Attempts (1 plan runs)

1. plan: passed (91.9 s)
1. policies: passed (1.7 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 8 model calls, 283 s)._
