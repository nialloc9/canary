output "database_name" {
  value = var.database_name
}

output "schema_names" {
  value = [for s in snowflake_schema.this : s.name]
  description = "Schema names"
}

output "schema_fqn" {
  value = [for s in snowflake_schema.this : "${var.database_name}.${s.name}"]
  description = "Fully qualified schema names"
}

output "landing_zone_schema_name" {
  value = snowflake_schema.this[0].name
  description = "Schema name for the landing zone"
}

output "landing_zone_schema_fqn" {
  value = "${var.database_name}.${snowflake_schema.this[0].name}"
  description = "Fully qualified schema name for the landing zone"
}