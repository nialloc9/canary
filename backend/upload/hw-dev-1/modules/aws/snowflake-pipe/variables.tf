variable "name" {
  description = "Landing zone name this pipe attaches to (matches the {name}-lz component)."
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 bucket to wire event notifications on (from the landing-zone module)."
  type        = string
}

variable "snowflake_database" {
  description = "Snowflake database containing the target schema and Bronze table."
  type        = string
}

variable "snowflake_schema" {
  description = "Snowflake schema containing the target Bronze table."
  type        = string
}

variable "stage_fqn" {
  description = "Fully-qualified external stage the pipe reads from (from the s3-storage-integration module)."
  type        = string
}

variable "target_table" {
  description = "Unqualified name of the Bronze table to create and load into."
  type        = string
}

variable "filter_prefix" {
  description = "S3 key prefix to filter event notifications."
  type        = string
  default     = ""
}

variable "filter_suffix" {
  description = "S3 key suffix to filter event notifications, e.g. .json"
  type        = string
  default     = ""
}
