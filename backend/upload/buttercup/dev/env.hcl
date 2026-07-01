locals {
  env_name         = "aura"
  env_type         = "dev"
  state_bucket     = "aura-infra-dev-terraform-state"
  state_region     = "eu-west-1"
  state_lock_table = "aura-infra-dev-terraform-lock"
}
