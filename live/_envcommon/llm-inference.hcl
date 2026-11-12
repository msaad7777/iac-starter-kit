terraform {
  source = "${get_repo_root()}/modules/gpu-inference"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

dependency "network" {
  config_path = "../network"

  # Lets plan run before the network exists. Apply always uses the real outputs.
  mock_outputs = {
    private_subnet_ids = ["subnet-00000000000000001", "subnet-00000000000000002"]
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]
}

inputs = {
  name       = "acme-${local.env.locals.environment}-llm"
  subnet_ids = dependency.network.outputs.private_subnet_ids
  # Placeholder AMI. In a real account read the AWS Deep Learning Base GPU AMI from its public SSM parameter.
  ami_id = "ami-0123456789abcdef0"
  tags   = { service = "llm-platform", data-classification = "confidential" }
}
