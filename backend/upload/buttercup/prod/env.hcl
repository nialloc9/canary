locals {
  env_name         = "buttercup-lz"
  env_type         = "prod"
  state_bucket     = "canary-test-1-prod-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "canary-test-1-prod-terraform-lock"
}
