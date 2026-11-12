include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${get_repo_root()}/live/_envcommon/llm-inference.hcl"
  expose = true
}

# Dev: all spot, and nothing runs outside office hours or at weekends.
inputs = {
  max_size         = 1
  desired_capacity = 1
  office_hours_schedule = {
    scale_up_cron   = "0 8 * * MON-FRI"
    scale_down_cron = "0 19 * * MON-FRI"
    time_zone       = "America/Toronto"
  }
}
