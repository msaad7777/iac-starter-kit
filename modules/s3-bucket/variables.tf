variable "name" {
  description = "Globally unique bucket name."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.name))
    error_message = "name must be a valid S3 bucket name (3-63 lowercase letters, digits, dots or hyphens)."
  }
}

variable "tags" {
  description = "Tags, normally the output of the tags module."
  type        = map(string)
}

variable "versioning" {
  description = "Keep previous object versions."
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "Customer managed KMS key. Leave null to use SSE-S3 (no KMS request charges)."
  type        = string
  default     = null
}

variable "intelligent_tiering_after_days" {
  description = "Move objects to S3 Intelligent-Tiering after this many days. 0 turns it off."
  type        = number
  default     = 30
  validation {
    condition     = var.intelligent_tiering_after_days >= 0
    error_message = "intelligent_tiering_after_days must be 0 or more."
  }
}

variable "noncurrent_version_expiration_days" {
  description = "Delete old object versions after this many days, so versioning does not grow cost forever."
  type        = number
  default     = 90
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a non-empty bucket. Keep false outside sandboxes."
  type        = bool
  default     = false
}
