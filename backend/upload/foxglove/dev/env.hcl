locals {
  env_name         = "aura"
  env_type         = "dev"
  state_bucket     = "aura-dev-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "aura-dev-terraform-lock"
}
