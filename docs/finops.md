# FinOps in the code, not in a spreadsheet

Cost control works best when the cheap choice is the default and the expensive one needs a reason in a pull request. This kit puts cost decisions in three places.

## 1. Defaults in the modules

| Module | Default | Saving |
|---|---|---|
| `network` | `nat_strategy = "single"` (one NAT gateway shared by all AZs); prod opts into `per_az` | NAT gateways are billed per hour each, plus per GB processed |
| `network` | free S3 and DynamoDB gateway endpoints | that traffic skips the NAT gateway's per-GB charge |
| `network` | flow logs off unless you pass an S3 bucket; when on, they go to S3, not CloudWatch Logs | flow logs are billed per GB ingested |
| `s3-bucket` | move objects to Intelligent-Tiering after 30 days | infrequently read data drops to cheaper tiers automatically |
| `s3-bucket` | expire old versions after 90 days; abort incomplete uploads after 7 | versioning and failed uploads stop growing storage forever |
| `s3-bucket` | S3 Bucket Keys whenever a KMS key is used | fewer KMS requests |
| `gpu-inference` | all spot above the base, three GPU types, `price-capacity-optimized` | spot GPU capacity is usually much cheaper than on-demand; more types mean fewer interruptions |
| `gpu-inference` | optional office-hours schedule that scales to zero in the evening and at weekends | idle GPUs are the largest waste in AI infrastructure |

## 2. Budgets and anomaly alerts as code

`modules/budget` creates a monthly AWS Budget with two alerts: actual spend above 80 percent and forecast spend above 100 percent. With `cost_center` set it only counts spend tagged with that cost centre (the Cost Explorer filter is `user:cost-center$CC-1234`). With `anomaly_detection = true` it also creates a Cost Anomaly Detection monitor per AWS service and a daily email subscription for anomalies above a dollar threshold. AWS allows one service-level monitor per account, so only the prod unit turns it on.

## 3. Policies that block waste before apply

The Kyverno policies in `policies/terraform` read the JSON plan:

- **require-finops-tags**: every taggable resource needs `cost-center`, `owner` and `environment` (directly or through `default_tags`), and Auto Scaling groups must propagate `cost-center` to the instances they launch.
- **gpu-spend-guardrails**: GPU groups must be at most 50 percent on-demand above the base, and dev GPU groups need a scale-to-zero schedule.
- **dev-nat-gateway-limit**: at most one NAT gateway outside prod.

### A real gap the tag policy found

Provider `default_tags` do not reach Auto Scaling group tags or launch template `tag_specifications`. The first version of `gpu-inference` only passed the module's own `tags`, so the GPU instances it launched would have had no `cost-center` tag and their spend would have been unallocated. The policy failed the dev and prod plans, and the module now merges `data.aws_default_tags` into the instance and volume tags.

## What this kit does not do yet

- **Cost estimates in pull requests.** Infracost can comment the monthly cost change of a plan, but its CLI needs a free API key from an Infracost account. It is not wired in, so the kit runs with no accounts at all.
- **Rightsizing and commitment planning** (Savings Plans, Reserved Instances). Those need real usage data.
