include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/snowflake/database"
}

inputs = {
  name    = "hw-dev-1"
  comment = "Dev database for hw-dev-1."
}
