variable "name" {
  description = "Budget name."
  type        = string
}

variable "monthly_limit_usd" {
  description = "Monthly budget in USD."
  type        = number
  validation {
    condition     = var.monthly_limit_usd > 0
    error_message = "monthly_limit_usd must be positive."
  }
}

variable "cost_center" {
  description = "Only count spend tagged with this cost-center. Null budgets the whole account. The tag must be activated as a cost allocation tag in the billing console first."
  type        = string
  default     = null
}

variable "alert_emails" {
  description = "Who gets budget and anomaly alerts."
  type        = list(string)
  validation {
    condition     = length(var.alert_emails) > 0 && alltrue([for e in var.alert_emails : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", e))])
    error_message = "Give at least one valid email address."
  }
}

variable "actual_threshold_percent" {
  description = "Alert when actual spend passes this percent of the budget."
  type        = number
  default     = 80
}

variable "forecast_threshold_percent" {
  description = "Alert when forecast spend passes this percent of the budget."
  type        = number
  default     = 100
}

variable "anomaly_detection" {
  description = "Create a Cost Anomaly Detection monitor per AWS service. AWS allows one such monitor per account, so turn this on in one place only."
  type        = bool
  default     = false
}

variable "anomaly_threshold_usd" {
  description = "Only alert on anomalies with at least this total impact in USD."
  type        = number
  default     = 50
}

variable "tags" {
  description = "Tags, normally the output of the tags module."
  type        = map(string)
}
