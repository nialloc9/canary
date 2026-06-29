
# Module specific variables

variable "force_destroy" {
  description = "A boolean that indicates all objects should be deleted from the bucket so that the bucket can be destroyed without error. Default set to false."
  type        = bool
  default     = false
}

variable "block_public_access" {
  description = "A boolean that indicates if public access to the bucket should be blocked. Default set to true."
  type        = bool
  default     = true
}

variable "versioning" {
  description = "Indicates if versioning should be enabled on the bucket. Default set to Enabled. Other options are Suspended and Disabled."
  type        = string
  default     = "Enabled"
}

variable "encrypt_at_rest" {
  description = "Indicates if server-side encryption with AES256 should be enabled for objects stored in the bucket. Default set to false."
  type        = bool
  default     = false
}

variable "policy" {
  description = "Policy to add to the bucket. Default set to empty string."
  type        = string
  default     = ""
}

variable "cors_rules" {
  default = []
}

locals {
  unique_name = "${var.name}-${random_string.random_string.result}"
  tags = merge(var.tags, {
    environment         = var.env
    projectName         = var.name
    department          = var.department
    createdBy           = var.created_by
    costCenter          = var.cost_center
    projectCode         = var.project_code
    team                = var.team
    owner               = var.owner
    data_classification = var.data_classification
  })
}