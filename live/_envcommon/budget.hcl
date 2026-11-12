terraform {
  source = "${get_repo_root()}/modules/budget"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name         = "acme-${local.env.locals.environment}"
  cost_center  = local.env.locals.cost_center
  alert_emails = ["finops@example.com"]
  tags         = { service = "finops", data-classification = "internal" }
}
