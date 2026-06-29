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
          AWS = snowflake_storage_integration.s3.storage_aws_iam_user_arn
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = snowflake_storage_integration.s3.describe_output[0].storage_aws_external_id[0].value
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

resource "snowflake_storage_integration" "s3" {
  name    = upper("${replace(var.name, "-", "_")}_S3_INTEGRATION")
  type    = "EXTERNAL_STAGE"
  enabled = true

  storage_provider     = "S3"
  storage_aws_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name}-snowflake-s3-role"

  storage_allowed_locations = ["s3://${var.s3_bucket_name}/"]

  comment = "Private Link storage integration for ${var.name}"
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
  name                = upper("${replace(var.name, "-", "_")}_S3_STAGE")
  database            = var.snowflake_database
  schema              = var.snowflake_schema
  storage_integration = snowflake_storage_integration.s3.name
  url                 = "s3://${var.s3_bucket_name}/${var.s3_stage_prefix}"

  comment = "External stage for ${var.name}"

  file_format         = upper("FORMAT_NAME = ${var.snowflake_database}.${var.snowflake_schema}.${snowflake_file_format.this.name}")
}
