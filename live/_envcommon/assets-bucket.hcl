terraform {
  source = "${get_repo_root()}/modules/s3-bucket"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name = "acme-${local.env.locals.environment}-model-artifacts"
  tags = { service = "llm-platform", data-classification = "confidential" }
}
