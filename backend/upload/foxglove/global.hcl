locals {
  project_name = "foxglove"

  common_tags = {
    project   = "${local.project_name}"
    terraform = "true"
  }
}
