resource "snowflake_database" "this" {
  name = upper(var.name)

  comment = var.comment
}