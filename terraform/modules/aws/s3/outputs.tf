output "bucket_arn" {
  description = "The ARN of the bucket."
  value       = aws_s3_bucket.bucket.arn
}

output "bucket_id" {
  description = "The name of the bucket."
  value       = aws_s3_bucket.bucket.id
}

output "bucket_region" {
  description = "The region of the bucket."
  value       = aws_s3_bucket.bucket.region
}