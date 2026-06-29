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

