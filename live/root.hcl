# Root Terragrunt configuration. Every unit under live/ includes this file.
#
# It does three things once, so units stay a few lines long:
#   1. generates the AWS provider, with the standard FinOps tags as default_tags
#   2. configures remote state (local for the offline demo, S3 for real accounts)
#   3. merges env.hcl and region.hcl into inputs
#
# Environment switches:
#   KIT_TARGET=moto      point the provider at a local Moto server (no AWS account needed)
#   KIT_TARGET=emulator  point it at a local AWS Emulator instead (scripts/emulator-env.sh)
#   KIT_BACKEND=s3   use the S3 backend with native lockfile locking (Terraform >= 1.10)

locals {
  env    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  region = read_terragrunt_config(find_in_parent_folders("region.hcl"))

  environment = local.env.locals.environment
  aws_region  = local.region.locals.aws_region
  cost_center = local.env.locals.cost_center
  owner       = local.env.locals.owner

  target  = get_env("KIT_TARGET", "aws")
  backend = get_env("KIT_BACKEND", "local")

  moto_url     = get_env("MOTO_URL", "http://localhost:5000")
  emulator_url = get_env("EMULATOR_URL", "https://127.0.0.1:9297")

  # Same keys as modules/tags. The provider applies them to every resource it creates.
  default_tags = {
    cost-center = local.cost_center
    owner       = local.owner
    environment = local.environment
    managed-by  = "terraform"
  }

  moto_provider_settings = <<-EOT
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = false
    s3_use_path_style           = true
    endpoints {
      autoscaling = "${local.moto_url}"
      budgets     = "${local.moto_url}"
      ce          = "${local.moto_url}"
      ec2         = "${local.moto_url}"
      iam         = "${local.moto_url}"
      s3          = "${local.moto_url}"
      s3control   = "${replace(local.moto_url, "127.0.0.1", "localhost")}"
      sts         = "${local.moto_url}"
    }
  EOT

  # AWS Emulator: HTTPS with a self-signed CA and run-only keys. Both come from the
  # environment (AWS_CA_BUNDLE, AWS_SHARED_CREDENTIALS_FILE) set by scripts/emulator-env.sh.
  # insecure: S3 Control (bucket tags in provider v6) prefixes the host with the account ID,
  # 000000000000.localhost, and the emulator's certificate only names localhost. Every
  # endpoint below is on this machine, so skipping verification never reaches real AWS.
  emulator_provider_settings = <<-EOT
    skip_metadata_api_check = true
    s3_use_path_style       = true
    insecure                = true
    endpoints {
      autoscaling = "${local.emulator_url}"
      budgets     = "${local.emulator_url}"
      ce          = "${local.emulator_url}"
      ec2         = "${local.emulator_url}"
      iam         = "${local.emulator_url}"
      s3          = "${local.emulator_url}"
      s3control   = "${replace(local.emulator_url, "127.0.0.1", "localhost")}"
      sts         = "${local.emulator_url}"
    }
  EOT

  local_provider_settings = lookup({
    moto     = local.moto_provider_settings
    emulator = local.emulator_provider_settings
  }, local.target, "")
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    provider "aws" {
      region = "${local.aws_region}"
      ${local.local_provider_settings}
      default_tags {
        tags = ${jsonencode(local.default_tags)}
      }
    }
  EOF
}

remote_state {
  backend = local.backend == "s3" ? "s3" : "local"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = local.backend == "s3" ? {
    bucket       = get_env("KIT_STATE_BUCKET")
    key          = "${path_relative_to_include()}/terraform.tfstate"
    region       = local.aws_region
    encrypt      = true
    use_lockfile = true
    } : {
    path = "${get_parent_terragrunt_dir()}/.state/${path_relative_to_include()}/terraform.tfstate"
  }
}

inputs = {
  environment = local.environment
  region      = local.aws_region
}
