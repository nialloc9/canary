locals {
  project_name = "buttercup"

  common_tags = {
    project   = "${local.project_name}"
    terraform = "true"
  }
}
