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

generate "provider" {
  path      = "provider.tf"
  if_exists = "skip"
  contents  = <<-EOF
    terraform {
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 5.0"
        }
        snowflake = {
          source  = "Snowflake-Labs/snowflake"
          version = "~> 0.87"
        }
        random = {
          source  = "hashicorp/random"
          version = "~> 3.0"
        }
        time = {
          source  = "hashicorp/time"
          version = "~> 0.9"
        }
      }
    }

    provider "aws" {
      region = "${local.aws_region}"
    }

    provider "snowflake" {
      preview_features_enabled = [
        "snowflake_table_resource",
        "snowflake_storage_integration_aws_resource",
        "snowflake_storage_integration_resource",
        "snowflake_file_format_resource",
        "snowflake_stage_resource",
        "snowflake_pipe_resource",
      ]
    }
  EOF
}
'''


def account_hcl() -> str:
    return '''locals {
  # Account-level overrides. Consumed by root terragrunt.hcl.
  # Add AWS account ID or other account-scoped values here.
}
'''


def _secret_suffix(stack_name: str) -> str:
    return stack_name.upper().replace("-", "_")


def ci_workflow(stacks: list[dict], infrastructure_base_path: str) -> str:
    """Generate the canary-infrastructure-deploy workflow.

    Each stack gets its own plan/apply job pair, scoped to its own
    subtree and its own suffixed Snowflake secrets — a stack's Snowflake
    identity can be a genuinely different Snowflake account, so a single
    shared job (as used when there was only ever "dev"/"prod") can't
    express this; the Snowflake provider reads identity purely from env
    vars, not from Terragrunt inputs.
    """
    secrets_doc = "\n".join(
        f"#   SNOWFLAKE_ORGANIZATION_NAME__{_secret_suffix(s['name'])} = {s['sf_organization_name']}\n"
        f"#   SNOWFLAKE_ACCOUNT_NAME__{_secret_suffix(s['name'])}      = {s['sf_account_name']}\n"
        f"#   SNOWFLAKE_USER__{_secret_suffix(s['name'])}              = {s['sf_user']}\n"
        f"#   SNOWFLAKE_PRIVATE_KEY_B64__{_secret_suffix(s['name'])}   = <base64-encoded PEM private key>\n"
        f"#   AWS_ACCESS_KEY_ID__{_secret_suffix(s['name'])}           = <AWS access key>\n"
        f"#   AWS_SECRET_ACCESS_KEY__{_secret_suffix(s['name'])}       = <AWS secret key>"
        for s in stacks
    )

    def _job(stack: dict, action: str, condition: str) -> str:
        suffix = _secret_suffix(stack["name"])
        title = action.capitalize()
        return f'''  {action}-{stack["name"]}:
    name: Terragrunt {title} ({stack["name"]})
    runs-on: ubuntu-latest
    if: {condition}
    env:
      SNOWFLAKE_ORGANIZATION_NAME: ${{{{ secrets.SNOWFLAKE_ORGANIZATION_NAME__{suffix} }}}}
      SNOWFLAKE_ACCOUNT_NAME: ${{{{ secrets.SNOWFLAKE_ACCOUNT_NAME__{suffix} }}}}
      SNOWFLAKE_USER: ${{{{ secrets.SNOWFLAKE_USER__{suffix} }}}}
      SNOWFLAKE_AUTHENTICATOR: jwt
      AWS_ACCESS_KEY_ID: ${{{{ secrets.AWS_ACCESS_KEY_ID__{suffix} }}}}
      AWS_SECRET_ACCESS_KEY: ${{{{ secrets.AWS_SECRET_ACCESS_KEY__{suffix} }}}}
      AWS_DEFAULT_REGION: {stack["region"]}
    steps:
      - uses: actions/checkout@v4

      - name: Decode Snowflake private key
        run: |
          echo "${{{{ secrets.SNOWFLAKE_PRIVATE_KEY_B64__{suffix} }}}}" | base64 -d > /tmp/sf_key.pem
          echo "SNOWFLAKE_PRIVATE_KEY=$(cat /tmp/sf_key.pem)" >> $GITHUB_ENV

      - uses: autero1/action-terragrunt@v3
        with:
          terragrunt_version: latest

      - name: {title}
        working-directory: {infrastructure_base_path}/{stack["name"]}
        run: terragrunt run-all {action} --terragrunt-non-interactive
'''

    branches = sorted({s["branch"] for s in stacks})
    branches_yaml = ", ".join(branches)

    plan_jobs = "\n".join(
        _job(s, "plan", f"github.event_name == 'pull_request' && github.base_ref == '{s['branch']}'")
        for s in stacks
    )
    apply_jobs = "\n".join(
        _job(s, "apply", f"github.event_name == 'push' && github.ref == 'refs/heads/{s['branch']}'")
        for s in stacks
    )

    return f'''name: canary-infrastructure-deploy

on:
  pull_request:
    branches: [{branches_yaml}]
    paths:
      - "{infrastructure_base_path}/**"
  push:
    branches: [{branches_yaml}]
    paths:
      - "{infrastructure_base_path}/**"

# Required GitHub secrets (one set per stack):
{secrets_doc}

jobs:
{plan_jobs}
{apply_jobs}'''


def bootstrap_workflow(stacks: list[dict]) -> str:
    """Generate the canary-bootstrap workflow.

    ``stacks`` must already be ordered by promotion order (i.e. account
    sort_order). Plan jobs run independently in parallel; apply jobs are
    chained so each stack only applies once the previous one has
    succeeded — this generalizes the old fixed `apply-prod needs
    [apply-dev]` dependency into an N-length chain.
    """

    def _plan_job(stack: dict) -> str:
        suffix = _secret_suffix(stack["name"])
        return f'''  plan-{stack["name"]}:
    name: Terraform Plan ({stack["name"]})
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' && github.base_ref == '{stack["branch"]}'
    env:
      AWS_ACCESS_KEY_ID: ${{{{ secrets.AWS_ACCESS_KEY_ID__{suffix} }}}}
      AWS_SECRET_ACCESS_KEY: ${{{{ secrets.AWS_SECRET_ACCESS_KEY__{suffix} }}}}
      AWS_DEFAULT_REGION: {stack["region"]}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Plan
        working-directory: bootstrap/{stack["name"]}
        run: |
          terraform init
          terraform plan
'''

    def _apply_job(stack: dict, previous: dict | None) -> str:
        suffix = _secret_suffix(stack["name"])
        needs = f'\n    needs: [apply-{previous["name"]}]' if previous else ""
        return f'''  apply-{stack["name"]}:
    name: Terraform Apply ({stack["name"]})
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/{stack["branch"]}'{needs}
    env:
      AWS_ACCESS_KEY_ID: ${{{{ secrets.AWS_ACCESS_KEY_ID__{suffix} }}}}
      AWS_SECRET_ACCESS_KEY: ${{{{ secrets.AWS_SECRET_ACCESS_KEY__{suffix} }}}}
      AWS_DEFAULT_REGION: {stack["region"]}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Apply
        working-directory: bootstrap/{stack["name"]}
        run: |
          terraform init
          terraform apply -auto-approve
'''

    branches_yaml = ", ".join(sorted({s["branch"] for s in stacks}))
    plan_jobs = "\n".join(_plan_job(s) for s in stacks)
    apply_jobs = "\n".join(
        _apply_job(s, stacks[i - 1] if i > 0 else None) for i, s in enumerate(stacks)
    )

    return f'''name: canary-bootstrap

on:
  pull_request:
    branches: [{branches_yaml}]
    paths:
      - "bootstrap/**"
  push:
    branches: [{branches_yaml}]
    paths:
      - "bootstrap/**"

jobs:
{plan_jobs}
{apply_jobs}'''


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


def env_hcl(account_slug: str, env: str, state_bucket: str, state_region: str, state_lock_table: str) -> str:
    return f'''locals {{
  env_name         = "{account_slug}"
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
    name = "MOCK_{name.upper().replace('-', '_')}"
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
  name         = "{name}"
  env          = "{env}"
  project_name = "{project_code}"{optional_inputs}

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
    s3_bucket_arn  = "arn:aws:s3:::MOCK_{name.upper().replace('-', '_')}_BUCKET"
    s3_bucket_name = "MOCK_{name.upper().replace('-', '_')}_BUCKET"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

dependency "db" {{
  config_path = "../{name}-db"

  mock_outputs = {{
    name = "MOCK_{name.upper().replace('-', '_')}"
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


def pipe_from_landing_zone(
    name: str,
    target_table: str,
    filter_prefix: str = "",
    filter_suffix: str = "",
) -> str:
    """Snowpipe terragrunt config, used both inline by `create_landing_zone`
    and standalone by `create_snowflake_pipe` (retrofitting an existing
    landing zone). Always wires up to the sibling {name}-db/-db-arch/-lz/-si
    components via dependency blocks rather than accepting literal database/
    schema strings — those names are transformed by the db/medallion-arch
    modules (uppercased, schema suffixed with its data classification), so
    a hand-typed literal is one typo away from a Snowflake "object does not
    exist" failure at apply time. Deriving them here means the pipe can
    never drift out of sync with the landing zone it belongs to.
    """
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
    s3_bucket_name = "MOCK_{name.upper().replace('-', '_')}_BUCKET"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

dependency "db" {{
  config_path = "../{name}-db"

  mock_outputs = {{
    name = "MOCK_{name.upper().replace('-', '_')}"
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

dependency "si" {{
  config_path = "../{name}-si"

  mock_outputs = {{
    stage_name = "MOCK_DB.MOCK_SCHEMA.MOCK_{name.upper().replace('-', '_')}_STAGE"
  }}
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}}

inputs = {{
  name               = "{name}"
  bucket_name        = dependency.lz.outputs.s3_bucket_name
  snowflake_database = dependency.db.outputs.name
  snowflake_schema   = dependency.db_arch.outputs.landing_zone_schema_name
  stage_fqn          = dependency.si.outputs.stage_name
  target_table       = "{target_table}"{optional_inputs}
}}
'''
