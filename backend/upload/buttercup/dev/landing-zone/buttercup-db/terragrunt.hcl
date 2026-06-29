include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/snowflake/database"
}

inputs = {
  name    = "buttercup"
  comment = "Dev database for buttercup."
}
