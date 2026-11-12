include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/assets-bucket.hcl"
  expose = true
}

inputs = {
  noncurrent_version_expiration_days = 90
}
