terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }
}

# Endpoints come from AWS_ENDPOINT_URL (scripts/moto-env.sh or emulator-env.sh) when running the demo.
provider "aws" {
  region   = "us-east-1"
  insecure = var.local_emulator_insecure_tls
}

# Only scripts/emulator-env.sh sets this: S3 Control calls go to 000000000000.localhost,
# a name the AWS Emulator's local certificate does not cover. Leave false for real accounts.
variable "local_emulator_insecure_tls" {
  type    = bool
  default = false
}
