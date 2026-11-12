variable "name" {
  description = "Name prefix for the launch template and Auto Scaling group."
  type        = string
}

variable "ami_id" {
  description = "AMI with GPU drivers, for example the AWS Deep Learning Base GPU AMI (look it up through its public SSM parameter)."
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id must look like ami-0123456789abcdef0."
  }
}

variable "instance_types" {
  description = "GPU instance types, in order of preference. Several types give spot more capacity pools to draw from."
  type        = list(string)
  default     = ["g6.xlarge", "g5.xlarge", "g4dn.xlarge"]
  validation {
    condition     = length(var.instance_types) > 0 && alltrue([for t in var.instance_types : can(regex("^(g[0-9]+[a-z]*|p[0-9]+[a-z]*|inf[0-9]+|trn[0-9]+[a-z]*)\\.[0-9a-z]+$", t))])
    error_message = "instance_types must be GPU or ML accelerator types (g*, p*, inf*, trn*)."
  }
}

variable "subnet_ids" {
  description = "Private subnets to launch into."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups for the instances."
  type        = list(string)
  default     = []
}

variable "min_size" {
  description = "Minimum instances during working hours."
  type        = number
  default     = 0
}

variable "max_size" {
  description = "Maximum instances."
  type        = number
  default     = 2
}

variable "desired_capacity" {
  description = "Instances to start with."
  type        = number
  default     = 1
}

variable "on_demand_base_capacity" {
  description = "How many instances are always on-demand. The rest use spot (often 60-70 percent cheaper but can be interrupted)."
  type        = number
  default     = 0
}

variable "on_demand_percentage_above_base" {
  description = "Percent of capacity above the base that is on-demand. 0 means all spot."
  type        = number
  default     = 0
  validation {
    condition     = var.on_demand_percentage_above_base >= 0 && var.on_demand_percentage_above_base <= 100
    error_message = "Must be between 0 and 100."
  }
}

variable "office_hours_schedule" {
  description = "Scale to zero outside office hours (cron in time_zone). Null keeps instances running around the clock."
  type = object({
    scale_up_cron   = string
    scale_down_cron = string
    time_zone       = string
  })
  default = null
}

variable "root_volume_gb" {
  description = "Root EBS volume size in GB (gp3, encrypted)."
  type        = number
  default     = 100
}

variable "instance_profile_name" {
  description = "IAM instance profile, for example one that can read model weights from S3."
  type        = string
  default     = null
}

variable "user_data" {
  description = "Startup script that pulls the model and starts the inference server."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags, normally the output of the tags module. They are copied to instances and volumes so GPU spend shows up per cost centre."
  type        = map(string)
}
