variable "name" {
  description = "Secret name/path in Secrets Manager, e.g. \"project_name/stack_name/secret_name\"."
  type        = string
}

variable "secret_string" {
  description = "Secret value to store (plain string, or a JSON-encoded string for structured secrets)."
  type        = string
  sensitive   = true
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to the secret."
  default     = {}
}
