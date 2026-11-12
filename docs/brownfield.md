# Brownfield: a team with resources made by hand (or by old scripts)

The goal is to bring existing resources under code **without recreating them**. The test of success is an import plan that says `0 to add, 0 to change, 0 to destroy`.

## The three steps

### 1. Discover

`brownfield/discover/discover.py` lists buckets, VPCs, subnets and security groups through read-only API calls and writes one Terraform `import` block per resource. It skips the default VPC, its subnets and default security groups, because nobody created those on purpose.

```bash
python brownfield/discover/discover.py --out imports.tf
```

### 2. Generate and review the configuration

Terraform 1.5 and later can write the configuration for import blocks:

```bash
terraform plan -generate-config-out=generated.tf
```

Treat the output as a draft. In this kit's demo (AWS provider 6.73) the raw file (`brownfield/discover/generated.raw.tf.txt`) did not plan at all. Terraform rejected its own output with five errors:

- subnet: `availability_zone` conflicts with `availability_zone_id` (reported once for each);
- subnet: `enable_lni_at_device_index must not be zero, got 0`;
- VPC: `ipv6_netmask_length` set without `ipv6_ipam_pool_id` (missing required argument);
- subnet: `map_customer_owned_ip_on_launch` set without the arguments it requires (missing required argument).

The reviewed version is `brownfield/discover/legacy.tf`. Besides fixing those errors it drops computed and null arguments and replaces hard-coded VPC IDs with references. Its plan is:

```
Plan: 4 to import, 0 to add, 0 to change, 0 to destroy.
```

### 3. Adopt into standard modules

Importing as plain resources is only half the job. `brownfield/adopt/main.tf` attaches the hand-made bucket to the kit's `s3-bucket` module with an import block that targets the module's resource:

```hcl
import {
  to = module.reports_bucket.aws_s3_bucket.this
  id = "acme-legacy-reports"
}
```

The plan then shows exactly what the module adds on top of the existing bucket:

```
Plan: 1 to import, 6 to add, 1 to change, 0 to destroy.
```

The six additions are the hardening the bucket was missing (public access block, ownership controls, encryption, versioning, lifecycle rules, TLS-only policy). The one change is the FinOps tags. Nothing is destroyed, so the data is never at risk. Review that list with the bucket's owner before applying, because versioning and lifecycle rules change storage cost.

`scripts/brownfield-demo.sh` runs all three steps against Moto and fails if either plan summary changes.

## Terraformer: the bulk-export option

[Terraformer](https://github.com/GoogleCloudPlatform/terraformer) exports whole services at once. Its repository was archived in March 2026, so it gets no new fixes. On the same demo estate it produced:

- 14 resources instead of 4: the default VPC, its six default subnets and two default security groups came along;
- names like `tfer--subnet-1bf5f134aebbf7561`, which need renaming with `moved` blocks;
- deprecated inline blocks on the bucket (`versioning`, `grant`);
- a provider pin of `~> 5.100.0`, a major version behind.

It also needs a named `default` profile (environment variables alone fail) and exits with status 0 even when every service fails, so `brownfield/terraformer/run_terraformer.sh` checks that files were actually generated. Use it for very large estates where listing resources is the hard part, then expect a long clean-up.

## Order for a real account

1. Read-only credentials only for discovery.
2. Import in small groups (one service or one team at a time). Each group must reach `0 to change` before the next starts.
3. Only after import, adopt resources into modules, one at a time, reviewing every addition.
4. Turn on the Kyverno plan policies in CI last, as warnings first, once the imported estate is mostly compliant.
