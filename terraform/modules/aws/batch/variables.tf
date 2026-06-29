variable "vpc_id" {
  type = string
}

variable "subnets" {
  type = list(string)
}

variable "security_groups" {
  type = list(string)
}

variable "instance_types" {
  type    = list(string)
  default = [
    "c7i.large",
    "c7i.xlarge",
    "c7i.2xlarge",
    "c6i.4xlarge",
    "c6i.8xlarge"
  ]
}

variable "max_vcpus" {
  type    = number
  default = 256
}

variable "desired_vcpus" {
  type    = number
  default = 0
}
