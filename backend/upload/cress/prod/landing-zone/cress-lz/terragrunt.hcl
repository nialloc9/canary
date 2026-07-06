include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/aws/landing-zone"
}

inputs = {
  name         = "cress"
  env          = "prod"
  project_name = "aura"
  existing_s3_bucket_arn = "arn:aws:s3:::linq-customer-cold-confidential-hw-cress-1-atmta068"

  create_access_keys = false

  transition_to_ia_days      = 0
  transition_to_glacier_days = 0
  expiration_days            = 30

  tags = {
    data_classification = "confidential"
    retention_policy    = "30-day"
    data_owner          = "engineering"
    department          = "none"
    cost_center         = "none"
    project_code        = "aura"
  }
}
