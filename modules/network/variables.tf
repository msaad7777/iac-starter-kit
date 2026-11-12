variable "name" {
  description = "Name prefix for every resource."
  type        = string
}

variable "cidr" {
  description = "VPC CIDR block."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.cidr))
    error_message = "cidr must be a valid IPv4 CIDR."
  }
}

variable "azs" {
  description = "Availability zones to spread subnets across, for example [\"us-east-1a\", \"us-east-1b\"]."
  type        = list(string)
  validation {
    condition     = length(var.azs) >= 1 && length(var.azs) <= 4
    error_message = "Use between 1 and 4 availability zones."
  }
}

variable "nat_strategy" {
  description = <<-EOT
    How private subnets reach the internet. NAT gateways are billed per hour and per GB.
      none   - no NAT (private subnets only reach AWS through VPC endpoints)
      single - one shared NAT gateway: cheapest, but one AZ failure cuts egress (good for dev)
      per_az - one NAT gateway per AZ: highly available (prod)
  EOT
  type        = string
  default     = "single"
  validation {
    condition     = contains(["none", "single", "per_az"], var.nat_strategy)
    error_message = "nat_strategy must be none, single or per_az."
  }
}

variable "gateway_endpoints" {
  description = "Free gateway endpoints. S3 and DynamoDB traffic then skips the NAT gateway's per-GB charge."
  type        = list(string)
  default     = ["s3", "dynamodb"]
}

variable "flow_logs_bucket_arn" {
  description = "S3 bucket ARN for VPC flow logs. S3 is far cheaper than CloudWatch Logs for this. Null turns flow logs off."
  type        = string
  default     = null
}

variable "region" {
  description = "AWS region, used for endpoint service names."
  type        = string
}

variable "tags" {
  description = "Tags, normally the output of the tags module."
  type        = map(string)
}
