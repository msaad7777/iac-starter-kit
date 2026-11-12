include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/budget.hcl"
  expose = true
}

inputs = {
  monthly_limit_usd = 2000
  # AWS allows one service-level anomaly monitor per account; prod owns it.
  anomaly_detection = true
}
