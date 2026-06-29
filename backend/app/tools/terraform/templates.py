def root() -> str:
    return '''locals {
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
'''


def account_hcl() -> str:
    return '''locals {
  # Account-level overrides. Consumed by root terragrunt.hcl.
  # Add AWS account ID or other account-scoped values here.
}
'''


def ci_workflow(
    snowflake_org: str,
    snowflake_account: str,
    snowflake_user: str,
    state_region: str,
    infrastructure_base_path: str,
) -> str:
    return f'''name: canary-infrastructure-deploy

on:
  pull_request:
    branches: [develop]
    paths:
      - "{infrastructure_base_path}/**"
  push:
    branches: [develop]
    paths:
      - "{infrastructure_base_path}/**"

env:
  SNOWFLAKE_ORGANIZATION_NAME: ${{{{ secrets.SNOWFLAKE_ORGANIZATION_NAME }}}}
  SNOWFLAKE_ACCOUNT_NAME: ${{{{ secrets.SNOWFLAKE_ACCOUNT_NAME }}}}
  SNOWFLAKE_USER: ${{{{ secrets.SNOWFLAKE_USER }}}}
  SNOWFLAKE_AUTHENTICATOR: jwt
  AWS_ACCESS_KEY_ID: ${{{{ secrets.AWS_ACCESS_KEY_ID }}}}
  AWS_SECRET_ACCESS_KEY: ${{{{ secrets.AWS_SECRET_ACCESS_KEY }}}}
  AWS_DEFAULT_REGION: {state_region}

# Required GitHub secrets:
#   SNOWFLAKE_ORGANIZATION_NAME = {snowflake_org}
#   SNOWFLAKE_ACCOUNT_NAME      = {snowflake_account}
#   SNOWFLAKE_USER              = {snowflake_user}
#   SNOWFLAKE_PRIVATE_KEY_B64   = <base64-encoded PEM private key>
#   AWS_ACCESS_KEY_ID           = <AWS access key>
#   AWS_SECRET_ACCESS_KEY       = <AWS secret key>

jobs:
  plan:
    name: Terragrunt Plan
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4

      - name: Decode Snowflake private key
        run: |
          echo "${{{{ secrets.SNOWFLAKE_PRIVATE_KEY_B64 }}}}" | base64 -d > /tmp/sf_key.pem
          echo "SNOWFLAKE_PRIVATE_KEY=$(cat /tmp/sf_key.pem)" >> $GITHUB_ENV

      - uses: autero1/action-terragrunt@v3
        with:
          terragrunt_version: latest

      - name: Plan
        working-directory: {infrastructure_base_path}
        run: terragrunt run-all plan --terragrunt-non-interactive

  apply:
    name: Terragrunt Apply
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/develop'
    steps:
      - uses: actions/checkout@v4

      - name: Decode Snowflake private key
        run: |
          echo "${{{{ secrets.SNOWFLAKE_PRIVATE_KEY_B64 }}}}" | base64 -d > /tmp/sf_key.pem
          echo "SNOWFLAKE_PRIVATE_KEY=$(cat /tmp/sf_key.pem)" >> $GITHUB_ENV

      - uses: autero1/action-terragrunt@v3
        with:
          terragrunt_version: latest

      - name: Apply
        working-directory: {infrastructure_base_path}
        run: terragrunt run-all apply --terragrunt-non-interactive
'''


def bootstrap_workflow(dev_state_region: str, prod_state_region: str) -> str:
    return f'''name: canary-bootstrap

on:
  pull_request:
    branches: [develop]
    paths:
      - "bootstrap/**"
  push:
    branches: [develop]
    paths:
      - "bootstrap/**"

env:
  AWS_ACCESS_KEY_ID: ${{{{ secrets.AWS_ACCESS_KEY_ID }}}}
  AWS_SECRET_ACCESS_KEY: ${{{{ secrets.AWS_SECRET_ACCESS_KEY }}}}

jobs:
  plan-dev:
    name: Terraform Plan (dev)
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    env:
      AWS_DEFAULT_REGION: {dev_state_region}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Plan
        working-directory: bootstrap/dev
        run: |
          terraform init
          terraform plan

  plan-prod:
    name: Terraform Plan (prod)
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    env:
      AWS_DEFAULT_REGION: {prod_state_region}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Plan
        working-directory: bootstrap/prod
        run: |
          terraform init
          terraform plan

  apply-dev:
    name: Terraform Apply (dev)
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/develop'
    env:
      AWS_DEFAULT_REGION: {dev_state_region}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Apply
        working-directory: bootstrap/dev
        run: |
          terraform init
          terraform apply -auto-approve

  apply-prod:
    name: Terraform Apply (prod)
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/develop'
    needs: [apply-dev]
    env:
      AWS_DEFAULT_REGION: {prod_state_region}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Apply
        working-directory: bootstrap/prod
        run: |
          terraform init
          terraform apply -auto-approve
'''


def global_hcl(name: str, extra_tags_hcl: str) -> str:
    common_tags_block = f"\n{extra_tags_hcl}" if extra_tags_hcl else ""
    return f'''locals {{
  project_name = "{name}"

  common_tags = {{
    project   = "${{local.project_name}}"
    terraform = "true"{common_tags_block}
  }}
}}
'''


def env_hcl(name: str, env: str, state_bucket: str, state_region: str, state_lock_table: str) -> str:
    return f'''locals {{
  env_name         = "{name}-lz"
  env_type         = "{env}"
  state_bucket     = "{state_bucket}"
  state_region     = "{state_region}"
  state_lock_table = "{state_lock_table}"
}}
'''


def region_hcl(region: str) -> str:
    return f'''locals {{
  aws_region = "{region}"
}}
'''


def db(name: str, env: str) -> str:
    return f'''include "base" {{
  path = find_in_parent_folders()
}}

terraform {{
  source = "${{get_parent_terragrunt_dir()}}/modules/snowflake/database"
}}

inputs = {{
  name    = "{name}"
  comment = "{env.title()} database for {name}."
}}
'''


def db_arch(name: str, data_classification: str, schemas_hcl: str) -> str:
    return f'''include "base" {{
  path = find_in_parent_folders()
}}

terraform {{
  source = "${{get_parent_terragrunt_dir()}}/modules/snowflake/medallion-arch"
}}

dependency "database" {{
  config_path = "../{name}-db"

  mock_outputs = {{
    name = "mock-{name}"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

inputs = {{
  database_name       = dependency.database.outputs.name
  data_classification = "{data_classification}"
  schema_names        = [{schemas_hcl}]
}}
'''


def state_bootstrap_main(bucket: str, region: str, lock_table: str) -> str:
    return f'''provider "aws" {{
  region = "{region}"
}}

resource "aws_s3_bucket" "state" {{
  bucket = "{bucket}"

  tags = {{
    Name    = "{bucket}"
    Purpose = "terraform-state"
  }}
}}

resource "aws_s3_bucket_versioning" "state" {{
  bucket = aws_s3_bucket.state.id

  versioning_configuration {{
    status = "Enabled"
  }}
}}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {{
  bucket = aws_s3_bucket.state.id

  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "aws:kms"
    }}
    bucket_key_enabled = true
  }}
}}

resource "aws_s3_bucket_public_access_block" "state" {{
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}

resource "aws_dynamodb_table" "lock" {{
  name         = "{lock_table}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {{
    name = "LockID"
    type = "S"
  }}

  tags = {{
    Name    = "{lock_table}"
    Purpose = "terraform-state-lock"
  }}
}}
'''


def state_bootstrap_outputs() -> str:
    return '''output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "state_bucket_arn" {
  value = aws_s3_bucket.state.arn
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}
'''


def state_bootstrap_versions() -> str:
    return '''terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
'''


def pipe(
    name: str,
    snowflake_database: str,
    snowflake_schema: str,
    target_table: str,
    filter_prefix: str = "",
    filter_suffix: str = "",
) -> str:
    optional_inputs = ""
    if filter_prefix:
        optional_inputs += f'\n  filter_prefix = "{filter_prefix}"'
    if filter_suffix:
        optional_inputs += f'\n  filter_suffix = "{filter_suffix}"'

    return f'''include "base" {{
  path = find_in_parent_folders()
}}

terraform {{
  source = "${{get_parent_terragrunt_dir()}}/modules/aws/snowflake-pipe"
}}

dependency "lz" {{
  config_path = "../{name}-lz"

  mock_outputs = {{
    bucket_id  = "mock-{name}-bucket"
    stage_name = "MOCK_DB.MOCK_SCHEMA.MOCK_{name.upper().replace("-", "_")}_STAGE"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

inputs = {{
  name               = "{name}"
  bucket_id          = dependency.lz.outputs.bucket_id
  snowflake_database = "{snowflake_database}"
  snowflake_schema   = "{snowflake_schema}"
  stage_fqn          = dependency.lz.outputs.stage_name
  target_table       = "{target_table}"{optional_inputs}
}}
'''


def lz(
    name: str,
    env: str,
    data_classification: str,
    retention_policy: str,
    data_owner: str,
    department: str,
    cost_center: str,
    project_code: str,
    create_access_keys: bool,
    transition_to_ia_days: int = 30,
    transition_to_glacier_days: int = 90,
    expiration_days: int = 365,
    existing_s3_bucket_arn: str = "",
    kms_key_arn: str = "",
) -> str:
    optional_inputs = ""
    if existing_s3_bucket_arn:
        optional_inputs += f'\n  existing_s3_bucket_arn = "{existing_s3_bucket_arn}"'
    if kms_key_arn:
        optional_inputs += f'\n  kms_key_arn            = "{kms_key_arn}"'

    return f'''include "base" {{
  path = find_in_parent_folders()
}}

terraform {{
  source = "${{get_parent_terragrunt_dir()}}/modules/aws/landing-zone"
}}

inputs = {{
  name = "{name}"
  env  = "{env}"{optional_inputs}

  create_access_keys = {str(create_access_keys).lower()}

  transition_to_ia_days      = {transition_to_ia_days}
  transition_to_glacier_days = {transition_to_glacier_days}
  expiration_days            = {expiration_days}

  tags = {{
    data_classification = "{data_classification}"
    retention_policy    = "{retention_policy}"
    data_owner          = "{data_owner}"
    department          = "{department}"
    cost_center         = "{cost_center}"
    project_code        = "{project_code}"
  }}
}}
'''


def si(
    name: str,
    s3_stage_prefix: str,
    file_format_type: str,
) -> str:
    return f'''include "base" {{
  path = find_in_parent_folders()
}}

terraform {{
  source = "${{get_parent_terragrunt_dir()}}/modules/snowflake/s3-storage-integration"
}}

dependency "lz" {{
  config_path = "../{name}-lz"

  mock_outputs = {{
    s3_bucket_arn  = "arn:aws:s3:::mock-{name}-bucket"
    s3_bucket_name = "mock-{name}-bucket"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

dependency "db" {{
  config_path = "../{name}-db"

  mock_outputs = {{
    name = "MOCK_{name.upper().replace("-", "_")}"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

dependency "db_arch" {{
  config_path = "../{name}-db-arch"

  mock_outputs = {{
    landing_zone_schema_name = "MOCK_LANDING_ZONE"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

inputs = {{
  name            = "{name}"
  s3_bucket_arn   = dependency.lz.outputs.s3_bucket_arn
  s3_bucket_name  = dependency.lz.outputs.s3_bucket_name
  s3_stage_prefix = "{s3_stage_prefix}"

  snowflake_database = dependency.db.outputs.name
  snowflake_schema   = dependency.db_arch.outputs.landing_zone_schema_name

  file_format_type = "{file_format_type}"
}}
'''
