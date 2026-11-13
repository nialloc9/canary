# ── S3 ───────────────────────────────────────────────────────────────────────

variable "existing_s3_bucket_arn" {
  description = "ARN of an existing S3 bucket to use instead of creating one. Leave empty to create a new bucket."
  type        = string
  default     = ""
}

variable "kms_key_arn" {
  description = "ARN of a KMS key for SSE-KMS on the S3 bucket. Leave empty to use the AWS-managed key."
  type        = string
  default     = ""
}

variable "create_access_keys" {
  description = "Whether to create an IAM user with access keys for S3 read/write access."
  type        = bool
  default     = false
}

# ── Lifecycle ─────────────────────────────────────────────────────────────────

variable "transition_to_ia_days" {
  description = "Days after creation before transitioning objects to STANDARD_IA. Set to 0 to skip."
  type        = number
  default     = 30
}

variable "transition_to_glacier_days" {
  description = "Days after creation before transitioning objects to GLACIER. Set to 0 to skip."
  type        = number
  default     = 90
}

variable "expiration_days" {
  description = "Days after creation before objects expire and are deleted. Set to 0 to disable."
  type        = number
  default     = 365
}

locals {
  unique_name    = lower(replace("${var.name}${var.env}${random_string.random_string.result}", "-", ""))
  create_bucket  = var.existing_s3_bucket_arn == ""
  bucket_arn     = local.create_bucket ? aws_s3_bucket.data[0].arn : var.existing_s3_bucket_arn
  bucket_name    = local.create_bucket ? aws_s3_bucket.data[0].bucket : replace(var.existing_s3_bucket_arn, "/arn:aws:s3:::/", "")
  tags = merge(var.tags, {
    environment         = var.env
    projectName         = var.name
  })
}