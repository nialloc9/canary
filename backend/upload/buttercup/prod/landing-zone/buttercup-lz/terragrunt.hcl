include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/aws/landing-zone"
}

inputs = {
  name = "buttercup"
  env  = "prod"

  create_access_keys = false

  transition_to_ia_days      = 30
  transition_to_glacier_days = 90
  expiration_days            = 365

  tags = {
    data_classification = "internal"
    retention_policy    = "1-year"
    data_owner          = "niall"
    department          = "engineering"
    cost_center         = "none"
    project_code        = "canary-test-1"
  }
}
