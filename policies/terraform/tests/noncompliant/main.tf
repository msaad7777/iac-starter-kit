# Deliberately non-compliant config. Each block breaks exactly one policy, so CI can prove
# every policy still catches what it is meant to catch. Plan only, never apply.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# require-finops-tags: no cost-center or owner
# s3-block-public-access: no public access block
resource "aws_s3_bucket" "untagged" {
  bucket = "acme-dev-shadow-it"
  tags   = { environment = "dev" }
}

# require-imdsv2: metadata tokens optional
resource "aws_launch_template" "gpu" {
  name_prefix = "gpu-"
  image_id    = "ami-0123456789abcdef0"
  metadata_options {
    http_tokens = "optional"
  }
  tags = { cost-center = "CC-1234", owner = "ml-team", environment = "dev" }
}

# gpu-spend-guardrails: 100 percent on-demand and no scale-to-zero schedule in dev
resource "aws_autoscaling_group" "gpu" {
  name                = "gpu-dev"
  min_size            = 0
  max_size            = 2
  vpc_zone_identifier = ["subnet-00000000000000001"]
  mixed_instances_policy {
    instances_distribution {
      on_demand_percentage_above_base_capacity = 100
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.gpu.id
      }
      override {
        instance_type = "g6.xlarge"
      }
    }
  }
  tag {
    key                 = "cost-center"
    value               = "CC-1234"
    propagate_at_launch = true
  }
  tag {
    key                 = "environment"
    value               = "dev"
    propagate_at_launch = true
  }
}

# dev-nat-gateway-limit: two NAT gateways in dev
resource "aws_eip" "nat" {
  count  = 2
  domain = "vpc"
  tags   = { cost-center = "CC-1234", owner = "platform-team", environment = "dev" }
}

resource "aws_nat_gateway" "extra" {
  count         = 2
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = "subnet-00000000000000001"
  tags          = { cost-center = "CC-1234", owner = "platform-team", environment = "dev" }
}
