mock_provider "aws" {
  mock_data "aws_default_tags" {
    defaults = {
      tags = { cost-center = "CC-1234", owner = "platform-team", environment = "dev" }
    }
  }
}

variables {
  name       = "llm-dev"
  ami_id     = "ami-0123456789abcdef0"
  subnet_ids = ["subnet-aaaa1111", "subnet-bbbb2222"]
  tags       = { cost-center = "CC-1234", environment = "dev" }
}

run "spot_first_by_default" {
  command = plan
  assert {
    condition     = aws_autoscaling_group.this.mixed_instances_policy[0].instances_distribution[0].on_demand_percentage_above_base_capacity == 0
    error_message = "Default should be all spot above the base."
  }
  assert {
    condition     = aws_autoscaling_group.this.mixed_instances_policy[0].instances_distribution[0].spot_allocation_strategy == "price-capacity-optimized"
    error_message = "Use price-capacity-optimized to lower interruption rates."
  }
  assert {
    condition     = length(aws_autoscaling_group.this.mixed_instances_policy[0].launch_template[0].override) == 3
    error_message = "Three GPU types give spot more capacity pools."
  }
}

run "hardened_launch_template" {
  command = plan
  assert {
    condition     = aws_launch_template.this.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be required."
  }
  assert {
    condition     = aws_launch_template.this.block_device_mappings[0].ebs[0].encrypted == "true"
    error_message = "Root volume must be encrypted."
  }
  assert {
    condition     = length(aws_launch_template.this.tag_specifications) == 2
    error_message = "Instances and volumes must both be tagged."
  }
}

run "tags_propagate_to_instances" {
  command = plan
  assert {
    condition     = alltrue([for t in aws_autoscaling_group.this.tag : t.propagate_at_launch])
    error_message = "ASG tags must propagate at launch."
  }
}

run "default_tags_reach_instances" {
  command = plan
  assert {
    condition     = anytrue([for t in aws_autoscaling_group.this.tag : t.key == "owner" && t.propagate_at_launch])
    error_message = "Provider default tags (owner) must be copied onto the ASG so instances get them."
  }
  assert {
    condition     = aws_launch_template.this.tag_specifications[0].tags["owner"] == "platform-team"
    error_message = "Provider default tags must reach instance tag_specifications."
  }
}

run "office_hours_schedule" {
  command = plan
  variables {
    office_hours_schedule = {
      scale_up_cron   = "0 8 * * MON-FRI"
      scale_down_cron = "0 19 * * MON-FRI"
      time_zone       = "America/Toronto"
    }
  }
  assert {
    condition     = aws_autoscaling_schedule.scale_down[0].desired_capacity == 0 && aws_autoscaling_schedule.scale_up[0].recurrence == "0 8 * * MON-FRI"
    error_message = "Schedule must scale to zero in the evening and back up in the morning."
  }
}

run "rejects_cpu_instance_types" {
  command = plan
  variables {
    instance_types = ["m7i.large"]
  }
  expect_failures = [var.instance_types]
}
