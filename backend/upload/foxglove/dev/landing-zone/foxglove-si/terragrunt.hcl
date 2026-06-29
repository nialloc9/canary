include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/snowflake/s3-storage-integration"
}

dependency "lz" {
  config_path = "../foxglove-lz"

  mock_outputs = {
    s3_bucket_arn  = "arn:aws:s3:::mock-foxglove-bucket"
    s3_bucket_name = "mock-foxglove-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "db" {
  config_path = "../foxglove-db"

  mock_outputs = {
    name = "MOCK_FOXGLOVE"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "db_arch" {
  config_path = "../foxglove-db-arch"

  mock_outputs = {
    landing_zone_schema_name = "MOCK_LANDING_ZONE"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  name            = "foxglove"
  s3_bucket_arn   = dependency.lz.outputs.s3_bucket_arn
  s3_bucket_name  = dependency.lz.outputs.s3_bucket_name
  s3_stage_prefix = "data/"

  snowflake_database = dependency.db.outputs.name
  snowflake_schema   = dependency.db_arch.outputs.landing_zone_schema_name

  file_format_type = "JSON"
}
