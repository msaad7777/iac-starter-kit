include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/network.hcl"
  expose = true
}

# Prod: three AZs and one NAT gateway per AZ, so losing an AZ does not cut egress for the others.
inputs = {
  cidr         = "10.20.0.0/16"
  azs          = ["us-east-1a", "us-east-1b", "us-east-1c"]
  nat_strategy = "per_az"
}
