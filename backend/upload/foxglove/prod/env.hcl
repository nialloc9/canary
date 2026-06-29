locals {
  env_name         = "foxglove-lz"
  env_type         = "prod"
  state_bucket     = "canary-test-1-prod-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "canary-test-1-prod-terraform-lock"
}
