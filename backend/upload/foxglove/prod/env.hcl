locals {
  env_name         = "aura"
  env_type         = "prod"
  state_bucket     = "aura-prod-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "aura-prod-terraform-lock"
}
