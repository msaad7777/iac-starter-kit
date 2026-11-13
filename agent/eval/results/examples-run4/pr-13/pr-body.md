## Request

> Staging GPU inference for team llm-serving, all spot, at most 3 instances, budget $1500.

Labels: none

## What this adds

| Env | Unit | Module | Settings |
|---|---|---|---|
| staging | `llm-serving-network` | `modules/network` | azs=["us-east-1a", "us-east-1b"], cidr="10.1.0.0/16", name="llm-serving-network", nat_strategy="single" |
| staging | `llm-serving-gpu` | `modules/gpu-inference` | ami_id="ami-0123456789abcdef0", instance_profile_name="llm-serving", instance_types=["g4dn.xlarge"], max_size=3, min_size=0, name="llm-serving-gpu", on_demand_base_capacity=0, on_demand_percentage_above_base=0, subnets from llm-serving-network |
| staging | `llm-serving-budget` | `modules/budget` | alert_emails=["finops@example.com"], cost_center="CC-1234", monthly_limit_usd=1500, name="llm-serving" |

## Plan (terragrunt plan against a local AWS mock; nothing applied)

| Plan | Actions | Resource types |
|---|---|---|
| staging-llm-serving-budget | 1 create | aws_budgets_budget ×1 |
| staging-llm-serving-gpu | 2 create | aws_autoscaling_group ×1, aws_launch_template ×1 |
| staging-llm-serving-network | 20 create | aws_eip ×1, aws_internet_gateway ×1, aws_nat_gateway ×1, aws_route ×3, aws_route_table ×3, aws_route_table_association ×4, aws_subnet ×4, aws_vpc ×1, aws_vpc_endpoint ×2 |

## Policy results (3 plan files, scripts/check-policies.sh)

| Plan | Pass | Fail |
|---|---|---|
| staging-llm-serving-budget.json | 5 | 0 |
| staging-llm-serving-gpu.json | 5 | 0 |
| staging-llm-serving-network.json | 5 | 0 |

## Decision record and diagram

- ADR draft: `docs/adr/0001-staging-gpu-inference-for-llm-serving.md`, status **Proposed**. Read it, fill in the deciders, set it to Accepted, then merge: CI fails while it is Proposed.
- Diagram drawn by code from the plan JSON: `docs/adr/0001-staging-gpu-inference-for-llm-serving.png` (16 resources with their own icon, 7 shown on a parent, 0 missed).

## Why these choices

- Created VPC with single NAT gateway per policy — Network
- Used spot instances only, max 3, no on-demand base — GPU
- Budget set to $1500 as requested — Budget

## Attempts (1 plan runs)

1. plan: passed (47.0 s)
1. policies: passed (0.8 s)

## Before merging

- Nothing was applied. CI plans and checks this again. CI has no apply step; if one is added, it runs after merge against Moto or the AWS Emulator only.
- Check the names, the owner and the cost centre: the agent fills defaults the request did not give.

_Written by kit-agent (gpt-oss:20b via Ollama, 8 model calls, 228 s)._
