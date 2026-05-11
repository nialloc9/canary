variable "bucket_name" {
  description = "Globally unique name for the S3 landing bucket."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of a KMS key to use for SSE-KMS encryption. If null, SSE-S3 (AES256) is used."
  type        = string
  default     = null
}

variable "transition_to_ia_days" {
  description = "Days after object creation before transitioning to STANDARD_IA."
  type        = number
  default     = 30
}

variable "transition_to_glacier_days" {
  description = "Days after object creation before transitioning to GLACIER."
  type        = number
  default     = 90
}

variable "expiration_days" {
  description = "Days after object creation before the object is deleted."
  type        = number
  default     = 365
}

variable "sqs_queue_arn" {
  description = "ARN of an SQS queue to notify on s3:ObjectCreated:* events (CSV files only). Set null to disable."
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags to apply to all resources."
  type        = map(string)
  default     = {}
}
