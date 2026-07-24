###############################################################################
# IAM Role for Snowflake
###############################################################################

resource "aws_iam_role" "snowflake_integration" {
  name = "${var.name}-snowflake-s3-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SnowflakeAssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = snowflake_storage_integration_aws.s3.describe_output[0].iam_user_arn
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = snowflake_storage_integration_aws.s3.describe_output[0].external_id
          }
        }
      }
    ]
  })

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_iam_role_policy" "snowflake_s3" {
  name = "${var.name}-snowflake-s3-policy"
  role = aws_iam_role.snowflake_integration.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}

###############################################################################
# Snowflake Storage Integration
###############################################################################

resource "snowflake_storage_integration_aws" "s3" {
  name    = upper("${replace(var.name, "-", "_")}_S3_INTEGRATION")
  enabled = true

  storage_provider     = "S3"
  storage_aws_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name}-snowflake-s3-role"

  storage_allowed_locations = ["s3://${var.s3_bucket_name}/"]

  comment = "Private Link storage integration for ${var.name}"
}

# Snowflake takes a few seconds to propagate a newly created storage
# integration internally — referencing it from a stage in the same apply
# (before that propagation finishes) fails with "Integration ... cannot be
# found" even though the integration was just created successfully.
#
# `triggers` is required, not optional: without it this only waits the
# *first* time the integration is ever created. If the integration is later
# replaced (e.g. someone deletes it in Snowflake directly and Terraform
# recreates it — exactly what "Marking the resource as removed" in a plan
# means), this resource has no config change of its own and Terraform
# leaves it alone, so the dependent stage gets no delay on that later
# recreate and hits the same race again. Tying `triggers` to the
# integration's id forces this to be replaced (and wait again) every time
# the integration is.
resource "time_sleep" "wait_for_storage_integration" {
  depends_on      = [snowflake_storage_integration_aws.s3]
  create_duration = "30s"

  triggers = {
    storage_integration_id = snowflake_storage_integration_aws.s3.id
  }
}

###############################################################################
# Snowflake Stage
###############################################################################

resource "snowflake_file_format" "this" {
  name        = "${upper(var.file_format_type)}_FF"
  database    = var.snowflake_database
  schema      = var.snowflake_schema
  format_type = upper(var.file_format_type)
}

resource "snowflake_stage" "s3" {
  depends_on = [time_sleep.wait_for_storage_integration]

  name                = upper("${replace(var.name, "-", "_")}_S3_STAGE")
  database            = var.snowflake_database
  schema              = var.snowflake_schema
  storage_integration = snowflake_storage_integration_aws.s3.name
  url                 = "s3://${var.s3_bucket_name}/${var.s3_stage_prefix}"

  comment = "External stage for ${var.name}"

  file_format         = upper("FORMAT_NAME = ${var.snowflake_database}.${var.snowflake_schema}.${snowflake_file_format.this.name}")
}
