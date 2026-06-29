variable "name" {
  type        = string
  description = "Project name"
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

locals {
  tags = merge(var.tags, {
    environment = var.env
    projectName = var.name
  })
  unique_name = lower(replace("${var.name}${random_string.random_string.result}", "-", ""))
}