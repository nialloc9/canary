output "unique_name" {
  description = "Generated unique name prefix used for all resources."
  value       = local.unique_name
}

output "s3_bucket_name" {
  description = "Name of the S3 data bucket."
  value       = local.bucket_name
}

output "s3_bucket_arn" {
  description = "ARN of the S3 data bucket."
  value       = local.bucket_arn
}

output "access_keys_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the S3 access keys."
  value       = var.create_access_keys ? aws_secretsmanager_secret.access_keys[0].arn : null
}
