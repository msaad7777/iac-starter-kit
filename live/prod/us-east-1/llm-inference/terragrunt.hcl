include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/llm-inference.hcl"
  expose = true
}

# Prod: one on-demand instance always serves traffic; extra capacity is spot.
inputs = {
  min_size                = 1
  max_size                = 4
  desired_capacity        = 2
  on_demand_base_capacity = 1
}
