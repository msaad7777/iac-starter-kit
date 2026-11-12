# Greenfield: a team with no infrastructure as code yet

This path is for a team that is starting fresh, or whose AWS accounts are small enough to rebuild. If you already have resources made by hand that must stay up, read [brownfield.md](brownfield.md) first.

## 1. Agree the tags before the first resource

Every module takes a `tags` map, and `live/root.hcl` sets the same keys as provider `default_tags`:

| Tag | Example | Why |
|---|---|---|
| `cost-center` | `CC-1234` | Finance can split the bill by budget owner |
| `owner` | `platform-team` | Someone is accountable for every dollar |
| `environment` | `dev`, `staging`, `prod` | Lets you compare environments and set different guardrails |
| `service` | `llm-platform` | Cost per product or service |
| `data-classification` | `internal` | Security reviews and S3 policies |
| `managed-by` | `terraform` | Spot resources made by hand |

`modules/tags` validates the format (for example `cost-center` must match `CC-1234`) so a typo fails at plan time, not at month end. Activate the tags as cost allocation tags in the AWS Billing console, or Cost Explorer cannot filter by them.

## 2. State before resources

Use one S3 bucket per organisation (or per account) for Terraform state, with versioning on. The S3 backend can lock state with a lock file in the same bucket (`use_lockfile = true`, added in Terraform 1.10 and generally available from 1.11), so a DynamoDB lock table is no longer needed. In this kit, `KIT_BACKEND=s3 KIT_STATE_BUCKET=<bucket>` switches `live/root.hcl` from local state to that S3 backend. The state key is the unit's path, for example `prod/us-east-1/network/terraform.tfstate`, so every unit has its own small state file and a mistake in one cannot corrupt another.

## 3. Layout: modules once, units per environment

```
modules/            reusable modules, versioned with the repo, tested with terraform test
live/
  root.hcl          provider, default tags, remote state: written once
  _envcommon/       what a unit is (module source and shared inputs)
  dev/  prod/       env.hcl (cost centre, owner) and one folder per unit
```

A unit such as `live/prod/us-east-1/network/terragrunt.hcl` only lists what is different in prod: three AZs and one NAT gateway per AZ instead of one shared gateway. Everything else comes from `_envcommon/network.hcl` and `root.hcl`. Adding a staging environment is copying `dev/` and changing `env.hcl`.

Units depend on each other through `dependency` blocks. `llm-inference` reads the private subnet IDs from `network`; `mock_outputs` lets you plan before the network exists, and apply always uses the real outputs.

## 4. Order of the first rollout

1. State bucket (by hand or a tiny bootstrap stack, then import it).
2. `budget` with anomaly detection in the production account, so overspend is caught from day one.
3. `network`.
4. Data and storage (`s3-bucket`).
5. Compute (`gpu-inference`, containers and so on).

## 5. Guardrails in CI

Every pull request runs:

- `terraform fmt`, `validate` and `terraform test` for each module (mock providers, no cloud account);
- Trivy misconfiguration scan;
- a plan for every unit, converted to JSON and checked by the Kyverno policies in `policies/terraform`;
- a test that every policy still fires on a deliberately non-compliant plan.

## Try it without an AWS account

The whole layout plans and applies against [Moto](https://github.com/getmoto/moto), a local AWS mock:

```bash
pip install "moto[server]" && moto_server -p 5000 &
source scripts/moto-env.sh
scripts/plan-json.sh dev && scripts/check-policies.sh
```

`scripts/moto-env.sh` sets `AWS_ENDPOINT_URL`, so any AWS call goes to Moto rather than a real account.
