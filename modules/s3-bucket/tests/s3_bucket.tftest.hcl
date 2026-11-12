mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  name = "acme-dev-checkout-assets"
  tags = { cost-center = "CC-1234", environment = "dev" }
}

run "secure_defaults" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_acls && aws_s3_bucket_public_access_block.this.restrict_public_buckets
    error_message = "Public access must be blocked."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.this.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "Default encryption should be SSE-S3 when no KMS key is given."
  }
  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning should be on by default."
  }
  assert {
    condition     = length(aws_s3_bucket_lifecycle_configuration.this.rule) == 3
    error_message = "Expected abort-uploads, intelligent-tiering and noncurrent-expiry rules."
  }
}

run "kms_turns_on_bucket_key" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:us-east-1:111122223333:key/11111111-2222-3333-4444-555555555555"
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.this.rule).bucket_key_enabled
    error_message = "Bucket keys must be on with KMS to limit request cost."
  }
}

run "tiering_can_be_turned_off" {
  command = plan
  variables {
    intelligent_tiering_after_days = 0
    versioning                     = false
  }
  assert {
    condition     = length(aws_s3_bucket_lifecycle_configuration.this.rule) == 1
    error_message = "Only the abort-uploads rule should remain."
  }
}

run "rejects_bad_name" {
  command = plan
  variables {
    name = "Bad_Bucket"
  }
  expect_failures = [var.name]
}
