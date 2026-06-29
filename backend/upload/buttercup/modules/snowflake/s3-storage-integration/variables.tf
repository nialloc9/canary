variable "name" {
  description = "Unique name prefix for all resources (typically passed from the landing-zone module)."
  type        = string
}

variable "s3_bucket_arn" {
  description = "ARN of the S3 bucket to integrate with Snowflake."
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket to integrate with Snowflake."
  type        = string
}

variable "s3_stage_prefix" {
  description = "Key prefix within the bucket that the Snowflake stage points at."
  type        = string
  default     = "data/"
}

variable "snowflake_database" {
  description = "Snowflake database in which the external stage will be created."
  type        = string
}

variable "snowflake_schema" {
  description = "Snowflake schema in which the external stage will be created."
  type        = string
}

variable "file_format_type" {
  description = "Snowflake file format type (e.g. JSON, CSV, PARQUET, AVRO, ORC, XML)."
  type        = string
  default     = "JSON"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags."
  default     = {}
}
