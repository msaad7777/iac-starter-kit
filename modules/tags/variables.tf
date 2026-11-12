variable "cost_center" {
  description = "Finance cost centre code, for example CC-1234."
  type        = string
  validation {
    condition     = can(regex("^CC-[0-9]{4}$", var.cost_center))
    error_message = "cost_center must look like CC-1234."
  }
}

variable "owner" {
  description = "Team or person accountable for the spend (an email or team handle)."
  type        = string
  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner must not be empty."
  }
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "service" {
  description = "Service or product the resources belong to."
  type        = string
}

variable "data_classification" {
  description = "Highest data class stored: public, internal, confidential or restricted."
  type        = string
  default     = "internal"
  validation {
    condition     = contains(["public", "internal", "confidential", "restricted"], var.data_classification)
    error_message = "data_classification must be public, internal, confidential or restricted."
  }
}

variable "extra" {
  description = "Additional tags. They cannot override the standard keys."
  type        = map(string)
  default     = {}
  validation {
    condition     = length(setintersection(keys(var.extra), ["cost-center", "owner", "environment", "service", "data-classification", "managed-by"])) == 0
    error_message = "extra must not redefine the standard tag keys."
  }
}
