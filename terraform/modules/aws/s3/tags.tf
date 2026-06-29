variable "department" {
  type        = string
  description = "Department name"
  default     = "none"
}

variable "name" {
  type        = string
  description = "Project name"
}

variable "env" {
  type        = string
  description = "Environment"
}

variable "location" {
  type        = string
  description = "The location of the resource group"
  default     = "West Europe"
}

variable "cost_center" {
  type        = string
  description = "The cost center of the resource group"
  default     = "none"
}

variable "project_code" {
  type        = string
  description = "The project code of the resource group"
  default     = "none"
}

variable "created_by" {
  type        = string
  description = "The created by of the resource group"
  default     = "terraform"
}

variable "team" {
  type        = string
  description = "The updated by of the resource group"
  default     = "none"
}

variable "owner" {
  type        = string
  description = "The owner of the resource group"
  default     = "none"
}

variable "data_classification" {
  type        = string
  description = "The data classification of the storage"
  default     = "undefined"
}

variable "tags" {
  type        = map(string)
  description = "The tags of the resource group"
  default     = {}
}