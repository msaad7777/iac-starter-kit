output "budget_name" {
  description = "Budget name."
  value       = aws_budgets_budget.this.name
}

output "anomaly_monitor_arn" {
  description = "Anomaly monitor ARN, or null when anomaly detection is off."
  value       = try(aws_ce_anomaly_monitor.services[0].arn, null)
}
