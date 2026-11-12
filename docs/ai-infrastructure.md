# AI infrastructure: GPU inference with guardrails

## On EC2: `modules/gpu-inference`

An Auto Scaling group for model serving (for example vLLM or Text Generation Inference on a Deep Learning AMI):

- **Spot first.** A mixed instances policy with `on_demand_base_capacity` (0 by default) and `on_demand_percentage_above_base` (0 by default), across `g6.xlarge`, `g5.xlarge` and `g4dn.xlarge`. `price-capacity-optimized` picks the spot pools least likely to be interrupted, and `capacity_rebalance` replaces instances that get a rebalance warning.
- **Prod keeps a floor.** The prod unit sets `on_demand_base_capacity = 1`, so one instance always serves traffic even if spot capacity disappears.
- **Office hours in dev.** `office_hours_schedule` adds two scheduled actions: scale to zero at 19:00 and back up at 08:00 on weekdays, in the team's time zone. `desired_capacity` is in `ignore_changes`, so `terraform apply` does not undo the schedule.
- **Hardened.** IMDSv2 required (`http_tokens = "required"`), encrypted gp3 root volume, launched into the private subnets from `network`, optional instance profile for reading model weights from S3.
- **Tagged where the money is.** Instances and volumes get the full tag set, including provider default tags (see [finops.md](finops.md) for why that needed an explicit merge).
- **Validated.** `instance_types` only accepts GPU and ML accelerator families (`g*`, `p*`, `inf*`, `trn*`).

Model weights belong in the `s3-bucket` module's bucket (`assets-bucket` unit), tagged `data-classification = confidential`.

## On Kubernetes: `policies/kubernetes`

For teams that serve models on EKS, three Kyverno policies (tested with `kyverno test`):

| Policy | Rule |
|---|---|
| `require-cost-labels` | Deployments, StatefulSets and Jobs need `cost-center` and `team` labels on the pod template, so tools such as OpenCost can split cluster cost |
| `gpu-workload-guardrails` | containers that request `nvidia.com/gpu` must set an equal limit; GPU pods must select spot nodes (`karpenter.sh/capacity-type: spot`) unless labelled `workload-tier: critical` |
| `require-pinned-images` | images need a version tag or digest, never `:latest`, because a model server that silently pulls a new image can change answers and memory use overnight |

## Pulumi version

`pulumi/` has a `SecureBucket` component with the same defaults as `modules/s3-bucket` and the same tag rules as `modules/tags`, for teams that prefer Python over HCL. Its unit tests use Pulumi's mocks, so they need no cloud account, no Pulumi Cloud login and no provider plugin.
