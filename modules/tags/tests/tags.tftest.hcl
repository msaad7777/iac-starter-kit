variables {
  cost_center = "CC-1234"
  owner       = "platform-team"
  environment = "dev"
  service     = "checkout"
}

run "standard_keys_present" {
  command = plan
  assert {
    condition     = output.tags["cost-center"] == "CC-1234" && output.tags["managed-by"] == "terraform"
    error_message = "Standard tags missing."
  }
  assert {
    condition     = output.tags["data-classification"] == "internal"
    error_message = "data_classification should default to internal."
  }
}

run "rejects_bad_cost_center" {
  command = plan
  variables {
    cost_center = "marketing"
  }
  expect_failures = [var.cost_center]
}

run "rejects_unknown_environment" {
  command = plan
  variables {
    environment = "qa"
  }
  expect_failures = [var.environment]
}

run "extra_cannot_override_standard_keys" {
  command = plan
  variables {
    extra = { owner = "someone-else" }
  }
  expect_failures = [var.extra]
}
