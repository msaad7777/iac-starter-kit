# Provider default_tags do not reach Auto Scaling group tags or launch template
# tag_specifications, so instances would launch without cost-center. Merge them in here.
data "aws_default_tags" "current" {}

locals {
  tags = merge(data.aws_default_tags.current.tags, var.tags)
}

resource "aws_launch_template" "this" {
  name_prefix            = "${var.name}-"
  image_id               = var.ami_id
  vpc_security_group_ids = var.security_group_ids
  user_data              = var.user_data == null ? null : base64encode(var.user_data)
  update_default_version = true

  # IMDSv2 only: stops SSRF-style credential theft through the metadata endpoint.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = var.root_volume_gb
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  dynamic "iam_instance_profile" {
    for_each = var.instance_profile_name == null ? [] : [var.instance_profile_name]
    content {
      name = iam_instance_profile.value
    }
  }

  # Tag instances and volumes, not only the template, so cost reports can see them.
  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { Name = var.name })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(local.tags, { Name = var.name })
  }

  tags = var.tags
}

resource "aws_autoscaling_group" "this" {
  name_prefix         = "${var.name}-"
  vpc_zone_identifier = var.subnet_ids
  min_size            = var.min_size
  max_size            = var.max_size
  desired_capacity    = var.desired_capacity
  capacity_rebalance  = true

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = var.on_demand_base_capacity
      on_demand_percentage_above_base_capacity = var.on_demand_percentage_above_base
      spot_allocation_strategy                 = "price-capacity-optimized"
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.this.id
        version            = "$Latest"
      }

      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  dynamic "tag" {
    for_each = local.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
    # The office-hours schedule changes desired capacity; do not fight it on every apply.
    ignore_changes = [desired_capacity]
  }
}

resource "aws_autoscaling_schedule" "scale_up" {
  count                  = var.office_hours_schedule == null ? 0 : 1
  scheduled_action_name  = "${var.name}-office-hours-up"
  autoscaling_group_name = aws_autoscaling_group.this.name
  recurrence             = var.office_hours_schedule.scale_up_cron
  time_zone              = var.office_hours_schedule.time_zone
  min_size               = var.min_size
  max_size               = var.max_size
  desired_capacity       = var.desired_capacity
}

resource "aws_autoscaling_schedule" "scale_down" {
  count                  = var.office_hours_schedule == null ? 0 : 1
  scheduled_action_name  = "${var.name}-office-hours-down"
  autoscaling_group_name = aws_autoscaling_group.this.name
  recurrence             = var.office_hours_schedule.scale_down_cron
  time_zone              = var.office_hours_schedule.time_zone
  min_size               = 0
  max_size               = var.max_size
  desired_capacity       = 0
}
