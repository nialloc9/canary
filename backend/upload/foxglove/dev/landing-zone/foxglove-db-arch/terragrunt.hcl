include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/snowflake/medallion-arch"
}

dependency "database" {
  config_path = "../foxglove-db"

  mock_outputs = {
    name = "MOCK_FOXGLOVE"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  database_name       = dependency.database.outputs.name
  data_classification = "confidential"
  schema_names        = ["bronze", "silver", "gold", "platinum"]
}
