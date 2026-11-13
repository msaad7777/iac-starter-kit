# AWS Emulator as a second local target

The kit runs everything against [Moto](https://github.com/getmoto/moto). In November 2026 AWS released [AWS Emulator](https://github.com/aws/aws-emulator) (CC0, no AWS account, no fee). This page records a trial of it as a second local target, with numbers measured on one machine, and what to do next.

- **Trialled:** AWS Emulator v1.0.338 (commit `32b3cf3`, released 2026-11-12), in Docker 29.5 on colima, macOS on Apple silicon (arm64). Terraform 1.11.4, AWS provider 6.73.0, Terragrunt 1.2.2, Kyverno CLI 1.20.0, boto3 1.44.2.
- **Compared with:** Moto 5.1 (`moto[server]==5.1.*`), on the same machine and the same day.
- **Never touched real AWS:** every run set `AWS_ENDPOINT_URL` to `127.0.0.1` and used the emulator's run-only keys or Moto's `test` keys.

## Result in one line

The emulator passes everything CI runs today, and it does the full apply, re-plan and destroy round trip **better** than Moto (no drift where Moto drifts, and budgets work). But two AWS calls the kit needs aren't implemented yet, and S3 Control needs TLS verification turned off. **Keep Moto as the CI default and add the emulator as an optional local target.** The CI job stays out until the round trip is fully green.

## Moto vs AWS Emulator

Times are wall-clock seconds for one run each, with Terraform providers already cached.

| Step | Moto 5.1 | AWS Emulator 1.0.338 |
|---|---|---|
| Setup | `uvx` start, ready in 2 s. On Linux CI, one `/etc/hosts` line for S3 Control. | No published image: build one from AWS's 8-line Dockerfile (50 s the first time), then ready in 2 s. New CA and keys on every start, read by `scripts/emulator-env.sh`. S3 Control needs `insecure = true` (see below). |
| `plan-json.sh dev` (4 units) | pass, 23 s | pass, 25 s |
| `plan-json.sh prod` (4 units) | pass, 20 s | pass, 23 s |
| `check-policies.sh` (8 plans × 5 policies) | pass, 2 s | pass, 2 s |
| `test-policies.sh` (5 policies fire on the bad plan) | pass, 4 s | pass, 4 s |
| `brownfield-demo.sh` | pass, 12 s: `4 to import/0/0/0`, then `1 to import/6 to add/1 to change/0 to destroy` | pass, 9 s, same two summaries. First try failed (`3 to import`) until the S3 Control fix below. |
| dev apply: network | 20 added, 11 s | 20 added, 12 s (NAT gateway, flow log and VPC endpoint included) |
| dev apply: assets-bucket | 7 added, 62 s | 7 added, 62 s. Both spend 55 s on `aws_s3_bucket_lifecycle_configuration`: the provider's own wait, not the target. |
| dev apply: budget | **hung.** Still creating after 8 min 40 s, stopped by hand. Moto has no `DescribeSubscribersForNotification`; the provider retries the 500. | 1 added, 10 s |
| dev apply: llm-inference | 4 added, 12 s | **failed**, 11 s. Launch template and Auto Scaling group created; both `aws_autoscaling_schedule` failed: `PutScheduledUpdateGroupAction ... NotImplemented` (HTTP 501). |
| dev re-plan right after apply | network: no changes. **assets-bucket: 2 to change** (bucket lost its `service` and `data-classification` tags; the policy re-reads). **llm-inference: 1 to change** (launch template lost `tag_specifications`). budget: not reached. | network, assets-bucket, budget: **no changes**. llm-inference: `2 to add` (only the two schedules that failed to create; **no drift** on what was created). |
| dev destroy | 7, 8 and 26 s; all destroyed | 7, 6, 8 and 26 s; all destroyed. Checked with boto3 afterwards: no VPCs, buckets, launch templates, groups, flow logs, addresses or budgets left (the NAT gateway reads `deleted`, as on AWS). |
| prod budget (anomaly detection on), extra check | not run | **failed.** Budget and anomaly monitor created, then `ce:ListTagsForResource ... NotImplemented` (501) on read. Plan and destroy fail the same way, so the unit can't be cleaned up through Terraform; restarting the emulator clears it. |

### The known Auto Scaling issue

The emulator's [`autoscaling-group-round-trip-create-skips-min-max`](https://github.com/aws/aws-emulator/tree/main/issues/things-that-do-not-work) issue says create doesn't validate `MinSize <= MaxSize` and describe omits some group defaults. It **doesn't bite** `gpu-inference`: the kit sends valid bounds, `DescribeAutoScalingGroups` returned `MinSize 0, MaxSize 1, DesiredCapacity 1`, both subnets, the mixed instances policy and all 6 tags, and the re-plan showed no change on the group. What does bite is a different gap: scheduled actions (`PutScheduledUpdateGroupAction`) aren't implemented, so the office-hours schedule can't be created.

## The S3 Control workaround (TLS)

AWS provider 6.x reads S3 bucket tags through S3 Control, and the SDK puts the account ID in front of the host: `https://000000000000.127.0.0.1:9297` doesn't resolve. Pointing S3 Control at `localhost` fixes the name (`000000000000.localhost` resolves to this machine on macOS), but the emulator's self-signed certificate only names `localhost`, `127.0.0.1` and `::1`:

```text
tls: failed to verify certificate: x509: certificate is valid for localhost, not 000000000000.localhost
```

The emulator has no option to choose its certificate, so the kit uses the provider's `insecure` setting, as a last resort and only for this target:

- `live/root.hcl` adds `insecure = true` and an S3 Control endpoint on `localhost` only when `KIT_TARGET=emulator`.
- `brownfield/discover` and `brownfield/adopt` read `insecure` from `var.local_emulator_insecure_tls` (default `false`), which only `scripts/emulator-env.sh` sets.
- boto3 still verifies the certificate through `AWS_CA_BUNDLE`.

Every endpoint is on this machine, so turning off verification can't send anything to real AWS. With the provider's default 25 retries, the TLS failure looked like a hang (stopped after 8 minutes); with `max_retries = 1` it failed in 2 s.

## How to run it

On macOS or Windows, build the image once from AWS's [Getting started with Docker](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html) Dockerfile, in an empty folder outside this repo. On Apple silicon, use `aws-emulator-aarch64.rpm` in the `ADD` line.

```bash
docker build -t aws-emulator .
```

Start it with telemetry off, open only on this machine:

```bash
mkdir -p ~/.aws/emulator
docker run -d --rm --name aws-emulator --memory=2g --memory-swap=2g -p 127.0.0.1:9297:9297 \
  -e HOME="$HOME" -v "$HOME/.aws/emulator:$HOME/.aws/emulator" aws-emulator -p 9297 --telemetry off
```

Then run the same steps as with Moto:

```bash
source scripts/emulator-env.sh
scripts/plan-json.sh dev && scripts/plan-json.sh prod
scripts/check-policies.sh
scripts/test-policies.sh
KIT_TARGET=emulator PYTHON="uvx --python 3.12 --with boto3 python" scripts/brownfield-demo.sh
```

The emulator has no reset API. Restart the container (`docker stop aws-emulator`, then run it again) before the brownfield demo; it keeps everything in memory and gets a new CA and new keys, so source `scripts/emulator-env.sh` again after each start.

## Recommendation

**Keep Moto, and add the emulator as an option (done on this branch).** Don't switch yet.

- **For:** it matches what CI checks, gives a cleaner apply round trip than Moto (no drift on the 30 resources it created, against 2 drifting resources on Moto), and supports budgets, where Moto hangs.
- **Against:** scheduled actions and Cost Explorer tags aren't implemented yet; S3 Control needs `insecure`; on macOS you build your own image and rebuild it for each release (AWS published three releases on the trial day).
- **CI:** no job added. The brief was to add one only if everything passes, and the round trip doesn't. When the two gaps move to the emulator's `issues/things-that-now-work/`, add an optional `apply-round-trip (AWS Emulator)` job beside the Moto job: install the `.deb` from AWS's [Linux guide](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-linux.html), start `aws-emulator --telemetry off &`, add `127.0.0.1 000000000000.localhost` to `/etc/hosts`, then apply, re-plan with `-detailed-exitcode` and destroy every dev unit.
- **Re-check:** dev llm-inference and prod budget on each new emulator release. Moto's drift on bucket tags and launch-template tag specifications is worth reporting upstream too.
