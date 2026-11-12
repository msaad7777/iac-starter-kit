include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/assets-bucket.hcl"
  expose = true
}

inputs = {
  # Dev artifacts are rebuilt often; keep old versions for two weeks only.
  noncurrent_version_expiration_days = 14
  force_destroy                      = true
}
