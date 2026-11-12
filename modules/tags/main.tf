# Standard FinOps tags. Every other module and the provider's default_tags use this
# map, so cost reports can always be split by cost centre, owner, environment and service.

locals {
  tags = merge(
    {
      cost-center         = var.cost_center
      owner               = var.owner
      environment         = var.environment
      service             = var.service
      data-classification = var.data_classification
      managed-by          = "terraform"
    },
    var.extra,
  )
}
