output "bucket_id" {
  description = "Name (ID) of the landing bucket."
  value       = aws_s3_bucket.landing.id
}

output "bucket_arn" {
  description = "ARN of the landing bucket."
  value       = aws_s3_bucket.landing.arn
}

output "bucket_domain_name" {
  description = "Bucket-regional domain name for use in policies or SDK config."
  value       = aws_s3_bucket.landing.bucket_regional_domain_name
}
