output "iam_role_arn" {
  description = "ARN of the IAM role assumed by Snowflake for S3 access."
  value       = aws_iam_role.snowflake_integration.arn
}

output "storage_integration_name" {
  description = "Name of the Snowflake storage integration."
  value       = snowflake_storage_integration.s3.name
}

output "stage_name" {
  description = "Fully-qualified name of the Snowflake external stage."
  value       = "${var.snowflake_database}.${var.snowflake_schema}.${snowflake_stage.s3.name}"
}

output "aws_iam_user_arn" {
  description = "Snowflake's IAM user ARN (add to the IAM role trust policy)."
  value       = snowflake_storage_integration.s3.storage_aws_iam_user_arn
}

output "aws_external_id" {
  description = "Snowflake's external ID (add to the IAM role trust policy)."
  value       = snowflake_storage_integration.s3.describe_output[0].storage_aws_external_id[0].value
  sensitive   = true
}
