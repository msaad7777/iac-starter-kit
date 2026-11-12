# Step 3: move the hand-made bucket under the kit's s3-bucket module.
# The import block attaches the existing bucket to the module's resource, so nothing is
# recreated. The plan then lists only the hardening the module adds on top.

module "tags" {
  source      = "../../modules/tags"
  cost_center = "CC-1234"
  owner       = "analytics-team"
  environment = "prod"
  service     = "reporting"
  extra       = { team = "analytics" }
}

module "reports_bucket" {
  source = "../../modules/s3-bucket"
  name   = "acme-legacy-reports"
  tags   = module.tags.tags
}

import {
  to = module.reports_bucket.aws_s3_bucket.this
  id = "acme-legacy-reports"
}
