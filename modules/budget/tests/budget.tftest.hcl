mock_provider "aws" {
  mock_resource "aws_ce_anomaly_monitor" {
    defaults = {
      arn = "arn:aws:ce::111122223333:anomalymonitor/00000000-0000-0000-0000-000000000000"
    }
  }
}

variables {
  name              = "checkout-dev"
  monthly_limit_usd = 500
  alert_emails      = ["finops@example.com"]
  tags              = { cost-center = "CC-1234" }
}

run "account_budget_without_filter" {
  command = plan
  assert {
    condition     = aws_budgets_budget.this.limit_amount == "500.00" && length(aws_budgets_budget.this.cost_filter) == 0
    error_message = "Without cost_center the budget covers the whole account."
  }
  assert {
    condition     = length(aws_ce_anomaly_monitor.services) == 0
    error_message = "Anomaly detection is off by default (one monitor per account)."
  }
}

run "cost_center_filter" {
  command = plan
  variables {
    cost_center = "CC-1234"
  }
  assert {
    condition     = contains(tolist(one(aws_budgets_budget.this.cost_filter).values), "user:cost-center$CC-1234")
    error_message = "Tag filter must use the user:<key>$<value> format."
  }
}

run "anomaly_detection" {
  variables {
    anomaly_detection = true
  }
  assert {
    condition     = length(aws_ce_anomaly_subscription.this) == 1 && aws_ce_anomaly_monitor.services[0].monitor_dimension == "SERVICE"
    error_message = "Anomaly monitor and subscription expected."
  }
}

run "rejects_bad_email" {
  command = plan
  variables {
    alert_emails = ["not-an-email"]
  }
  expect_failures = [var.alert_emails]
}
