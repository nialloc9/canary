variable "schema_names" {
  description = "List of schema names"
  type        = list(string)
  default     = ["bronze", "silver", "gold", "platinum"]
}

variable "database_name" {
  description = "Name of the database"
  type        = string
}