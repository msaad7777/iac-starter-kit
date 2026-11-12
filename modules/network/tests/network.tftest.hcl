mock_provider "aws" {}

variables {
  name   = "acme-dev"
  cidr   = "10.40.0.0/16"
  azs    = ["us-east-1a", "us-east-1b", "us-east-1c"]
  region = "us-east-1"
  tags   = { cost-center = "CC-1234" }
}

run "single_nat_for_dev" {
  command = plan
  assert {
    condition     = length(aws_nat_gateway.this) == 1 && length(aws_route.private_nat) == 3
    error_message = "single strategy: one NAT gateway shared by three private route tables."
  }
  assert {
    condition     = length(aws_subnet.private) == 3 && aws_subnet.private[0].cidr_block == "10.40.128.0/20"
    error_message = "Private subnets should start at the second half of the VPC range."
  }
  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == false])
    error_message = "Public subnets must not auto-assign public IPs."
  }
  assert {
    condition     = length(aws_vpc_endpoint.gateway) == 2
    error_message = "S3 and DynamoDB gateway endpoints are free and should be on by default."
  }
}

run "per_az_nat_for_prod" {
  command = plan
  variables {
    nat_strategy = "per_az"
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 3
    error_message = "per_az strategy: one NAT gateway per AZ."
  }
}

run "no_nat" {
  command = plan
  variables {
    nat_strategy = "none"
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 0 && length(aws_route.private_nat) == 0 && length(aws_eip.nat) == 0
    error_message = "none strategy: no NAT gateways, EIPs or default routes."
  }
}

run "flow_logs_only_when_bucket_given" {
  command = plan
  variables {
    flow_logs_bucket_arn = "arn:aws:s3:::acme-flow-logs"
  }
  assert {
    condition     = length(aws_flow_log.this) == 1 && aws_flow_log.this[0].log_destination_type == "s3"
    error_message = "Flow logs should go to S3 when a bucket is given."
  }
}

run "rejects_bad_strategy" {
  command = plan
  variables {
    nat_strategy = "two"
  }
  expect_failures = [var.nat_strategy]
}
