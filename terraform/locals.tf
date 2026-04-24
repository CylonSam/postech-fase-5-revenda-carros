locals {
  name_prefix = var.project_name

  common_tags = {
    Project   = var.project_name
    ManagedBy = "Terraform"
    Owner     = "postech-grad"
  }
}
