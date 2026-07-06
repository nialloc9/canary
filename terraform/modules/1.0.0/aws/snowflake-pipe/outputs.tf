output "pipe_name" {
  description = "Fully-qualified name of the Snowflake pipe."
  value       = "${var.snowflake_database}.${var.snowflake_schema}.${snowflake_pipe.this.name}"
}

output "notification_channel" {
  description = "ARN of the SQS queue Snowflake manages for auto-ingest notifications."
  value       = snowflake_pipe.this.notification_channel
}

output "bronze_table_name" {
  description = "Name of the Bronze table created for this pipe."
  value       = snowflake_table.bronze.name
}

output "bronze_table_fqn" {
  description = "Fully-qualified name of the Bronze table created for this pipe."
  value       = "${var.snowflake_database}.${var.snowflake_schema}.${snowflake_table.bronze.name}"
}
