# Landing Zone — S3 + Snowflake Storage Integration

Creates an S3 bucket with a Snowflake storage integration and external stage, allowing Snowflake to read and write data directly from S3.

## What it creates

| Resource | Description |
| --- | --- |
| `aws_s3_bucket` | Versioned, SSE-KMS encrypted bucket with public access blocked |
| `aws_iam_role` | IAM role assumed by Snowflake via `sts:AssumeRole` |
| `aws_iam_role_policy` | Inline policy granting S3 read/write/list on the bucket |
| `snowflake_storage_integration` | Links the S3 bucket to Snowflake via the IAM role |
| `snowflake_file_format` | JSON file format used by the stage |
| `snowflake_stage` | External stage pointing at the S3 bucket prefix |

## Prerequisites

1. **Snowflake provider configured** — the root `terragrunt.hcl` configures the provider using an unencrypted PKCS8 private key at `/tmp/snowflake_key.p8`. Generate one with:

    ```bash
    make generate_keys
    ```

2. **Snowflake database and schema** — deploy the `foxglove-db` and `foxglove-db-arch` stacks first (the terragrunt dependencies handle this automatically).

3. **Snowflake IAM user ARNs** — get these from your Snowflake account. Run in Snowflake:

    ```sql
    SELECT SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO();
    ```

## Usage

```hcl
# terragrunt.hcl
terraform {
  source = "${get_repo_root()}/modules/landing-zone"
}

inputs = {
  name = "foxglovelz"
  env  = "prod"

  snowflake_database = dependency.db.outputs.name
  snowflake_schema   = dependency.db_arch.outputs.landing_zone_schema_name

  snowflake_account_aws_user_arn = [
    "arn:aws:iam::672255977428:user/t1190000-s",
    "arn:aws:iam::378686993667:user/bm221000-s"
  ]
}
```

## Deployment

The IAM trust policy references the Snowflake IAM user ARNs, which must be known at plan time. Supply them via `snowflake_account_aws_user_arn`.

```bash
# Validate and plan
make predeploy ENV=prod PROJECT_NAME=landing-zone/foxglove-lz

# Apply
make apply ENV=prod PROJECT_NAME=landing-zone/foxglove-lz
```

After apply, verify the integration works in Snowflake:

```sql
DESC INTEGRATION <integration_name>;
LIST @<database>.<schema>.<stage_name>;
```

## Inputs

| Name | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `name` | string | — | yes | Project name |
| `env` | string | — | yes | Environment (e.g. `dev`, `prod`) |
| `snowflake_database` | string | — | yes | Snowflake database for the stage |
| `snowflake_schema` | string | — | yes | Snowflake schema for the stage |
| `snowflake_account_aws_user_arn` | list(string) | `[]` | yes | Snowflake IAM user ARNs for the trust policy |
| `s3_stage_prefix` | string | `"data/"` | no | S3 key prefix the stage points at |
| `kms_key_arn` | string | `""` | no | KMS key ARN for SSE (empty = AWS managed key) |
| `tags` | map(string) | `{}` | no | Tags applied to all resources |

## Outputs

| Name | Description |
| --- | --- |
| `s3_bucket_name` | Name of the S3 data bucket |
| `s3_bucket_arn` | ARN of the S3 data bucket |
| `snowflake_iam_role_arn` | IAM role ARN assumed by Snowflake |
| `snowflake_storage_integration_name` | Name of the Snowflake storage integration |
| `snowflake_stage_name` | Fully-qualified stage name (`db.schema.stage`) |
| `snowflake_aws_iam_user_arn` | Snowflake's IAM user ARN (from the integration) |
| `snowflake_aws_external_id` | Snowflake's external ID (sensitive) |
