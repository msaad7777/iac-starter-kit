# Hand-reviewed version of generated.raw.tf.txt (what `terraform plan -generate-config-out`
# produced). Changes from the raw output:
#   - dropped computed and null arguments, and the conflicting availability_zone_id
#   - dropped enable_lni_at_device_index = 0, which the provider rejects
#   - replaced hard-coded VPC IDs with references
#   - split inline security group rules into separate rule resources is left for
#     the next step; inline rules are kept so the import plan shows zero changes

resource "aws_vpc" "legacy_vpc" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = false
  tags = {
    Name = "legacy-vpc"
  }
}

resource "aws_subnet" "legacy_app" {
  vpc_id            = aws_vpc.legacy_vpc.id
  cidr_block        = "10.30.1.0/24"
  availability_zone = "us-east-1a"
  tags = {
    Name = "legacy-app"
  }
}

resource "aws_security_group" "legacy_web" {
  name        = "legacy-web"
  description = "made by hand"
  vpc_id      = aws_vpc.legacy_vpc.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_s3_bucket" "acme_legacy_reports" {
  bucket = "acme-legacy-reports"
  tags = {
    team = "analytics"
  }
}
