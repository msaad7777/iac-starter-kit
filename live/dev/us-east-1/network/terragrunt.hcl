include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/network.hcl"
  expose = true
}

# Dev: two AZs and one shared NAT gateway (cheapest; an AZ outage only affects dev egress).
inputs = {
  cidr         = "10.10.0.0/16"
  azs          = ["us-east-1a", "us-east-1b"]
  nat_strategy = "single"
}
