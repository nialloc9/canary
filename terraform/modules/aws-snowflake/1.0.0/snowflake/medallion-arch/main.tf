resource "snowflake_schema" "this" {
  count = length(var.schema_names)
  name     = upper("${var.schema_names[count.index]}_${var.data_classification}")
  database = var.database_name

  comment             = "Schema for ${var.schema_names[count.index]} data with ${var.data_classification} classification"
  is_transient        = false

  lifecycle {
    prevent_destroy = true
  }
}

