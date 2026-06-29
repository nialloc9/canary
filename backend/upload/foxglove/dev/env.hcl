locals {
  env_name         = "foxglove-lz"
  env_type         = "dev"
  state_bucket     = "canary-test-1-dev-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "canary-test-1-dev-terraform-lock"
}
