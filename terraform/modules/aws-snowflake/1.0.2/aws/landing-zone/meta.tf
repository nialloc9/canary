variable "name" {
  type        = string
  description = "Landing zone name"
}

variable "project_name" {
  type        = string
  description = "Project name — used as the top-level path segment for any Secrets Manager secrets this module creates."
}

variable "env" {
  type        = string
  description = "Environment"
}

variable "tags" {
  type        = map(string)
  description = "The tags of the resource group"
  default     = {}
}

