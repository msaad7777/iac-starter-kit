## Request

> Staging network for team checkout with 3 availability zones; budget $400.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| staging | `checkout-network` | `modules/network` | azs=["us-east-1a", "us-east-1b", "us-east-1c"], cidr="10.2.0.0/16", name="checkout", nat_strategy="single" |
| staging | `checkout-budget` | `modules/budget` | actual_threshold_percent=80, alert_emails=["finops@example.com"], anomaly_threshold_usd=100, cost_center="CC-1234", monthly_limit_usd=400, name="checkout" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| staging-checkout-budget | 1 create | aws_budgets_budget ×1 |
| staging-checkout-network | 26 create | aws_eip ×1, aws_internet_gateway ×1, aws_nat_gateway ×1, aws_route ×4, aws_route_table ×4, aws_route_table_association ×6, aws_subnet ×6, aws_vpc ×1, aws_vpc_endpoint ×2 |

## Policy results (2 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| staging-checkout-budget.json | 5 | 0 |
| staging-checkout-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-staging-network-and-budget-for-checkout.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-staging-network-and-budget-for-checkout.png` (17 resources with their own icon, 10 shown on a parent, 0 missed).

## Why these choices

- Created VPC with 3 AZs and single NAT gateway compliant with policy — Network
- Budget set to $400 with alert thresholds — Budget

## Attempts (1 plan runs)

1. plan: passed (30.9 s)
1. policies: passed (0.6 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 8 model calls, 207 s)._
