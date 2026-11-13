## Request

> Give the data team in dev a network across two availability zones with one NAT gateway, and a budget of $300 a month.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| dev | `data-network` | `modules/network` | azs=["us-east-1a", "us-east-1b"], cidr="10.1.0.0/16", name="data", nat_strategy="single" |
| dev | `data-budget` | `modules/budget` | alert_emails=["finops@example.com"], monthly_limit_usd=300, name="data" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| dev-data-budget | 1 create | aws_budgets_budget ×1 |
| dev-data-network | 20 create | aws_eip ×1, aws_internet_gateway ×1, aws_nat_gateway ×1, aws_route ×3, aws_route_table ×3, aws_route_table_association ×4, aws_subnet ×4, aws_vpc ×1, aws_vpc_endpoint ×2 |

## Policy results (6 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| dev-assets-bucket.json | 5 | 0 |
| dev-budget.json | 5 | 0 |
| dev-data-budget.json | 5 | 0 |
| dev-data-network.json | 5 | 0 |
| dev-llm-inference.json | 5 | 0 |
| dev-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-add-dev-data-network-with-single-nat-gat.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-add-dev-data-network-with-single-nat-gat.png` (14 resources with their own icon, 7 shown on a parent, 0 missed).

## Why these choices

- network — two AZs, single NAT gateway
- budget — $300/month limit

## Attempts (1 plan runs)

1. plan: passed (89.2 s)
1. policies: passed (1.7 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 8 model calls, 267 s)._
