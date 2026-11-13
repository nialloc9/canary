# Bronze table: Terraform owns only this minimal, generic ingestion shape.
# Silver/Gold modeling is dbt's responsibility from here on — this table's
# columns are never redefined by dbt, only selected from.
resource "snowflake_table" "bronze" {
  database = var.snowflake_database
  schema   = var.snowflake_schema
  name     = upper(var.target_table)

  column {
    name = "RAW_DATA"
    type = "VARIANT"
  }

  column {
    name = "SOURCE_FILE"
    type = "VARCHAR"
  }

  column {
    name = "LOAD_TIMESTAMP"
    type = "TIMESTAMP_NTZ"

    default {
      expression = "CURRENT_TIMESTAMP()"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "snowflake_pipe" "this" {
  database = var.snowflake_database
  schema   = var.snowflake_schema
  # Includes target_table (not just the landing zone name) so a landing zone
  # with more than one table/pipe never collides on the same Snowflake pipe
  # object name.
  name     = upper("${replace(var.name, "-", "_")}_${replace(var.target_table, "-", "_")}_PIPE")

  copy_statement = <<-SQL
    COPY INTO ${var.snowflake_database}.${var.snowflake_schema}.${snowflake_table.bronze.name} (RAW_DATA, SOURCE_FILE, LOAD_TIMESTAMP)
    FROM (
      SELECT $1, METADATA$FILENAME, CURRENT_TIMESTAMP()
      FROM @${var.stage_fqn}
    )
  SQL

  auto_ingest = true
}

resource "aws_s3_bucket_notification" "snowpipe" {
  bucket = var.bucket_name

  queue {
    queue_arn     = snowflake_pipe.this.notification_channel
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = var.filter_prefix
    filter_suffix = var.filter_suffix
  }
}
