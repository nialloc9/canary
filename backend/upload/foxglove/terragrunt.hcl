locals {
  global_vars  = read_terragrunt_config(find_in_parent_folders("global.hcl", "does-not-exist.fallback"), { locals = {} })
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl", "does-not-exist.fallback"), { locals = {} })
  region_vars  = read_terragrunt_config("region.hcl", read_terragrunt_config(find_in_parent_folders("region.hcl", "does-not-exist.fallback"), { locals = {} }))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl", "does-not-exist.fallback"), { locals = {} })

  project_name     = local.global_vars.locals.project_name
  common_tags      = local.global_vars.locals.common_tags
  aws_region       = local.region_vars.locals.aws_region
  state_bucket     = local.env_vars.locals.state_bucket
  state_region     = local.env_vars.locals.state_region
  state_lock_table = local.env_vars.locals.state_lock_table
}

remote_state {
  backend = "s3"
  config = {
    bucket         = local.state_bucket
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = local.state_region
    encrypt        = true
    dynamodb_table = local.state_lock_table
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

inputs = merge(
  local.global_vars.locals,
  local.region_vars.locals,
  local.env_vars.locals,
)

generate "provider" {{
  path      = "provider.tf"
  if_exists = "skip"
  contents  = <<-EOF
    terraform {{
      required_providers {{
        aws = {{
          source  = "hashicorp/aws"
          version = "~> 5.0"
        }}
        snowflake = {{
          source  = "Snowflake-Labs/snowflake"
          version = "~> 0.87"
        }}
        random = {{
          source  = "hashicorp/random"
          version = "~> 3.0"
        }}
      }}
    }}

    provider "aws" {{
      region = "${{local.aws_region}}"
    }}

    provider "snowflake" {{}}
  EOF
}}
