# Shared settings for the network unit. Each environment includes this and overrides what differs.
terraform {
  source = "${get_repo_root()}/modules/network"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name = "acme-${local.env.locals.environment}"
  tags = { service = "shared-network", data-classification = "internal" }
}
