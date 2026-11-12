terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }
}

# Endpoints come from AWS_ENDPOINT_URL (scripts/moto-env.sh) when running the demo.
provider "aws" {
  region = "us-east-1"
}
