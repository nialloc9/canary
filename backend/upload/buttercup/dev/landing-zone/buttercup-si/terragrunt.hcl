include "base" {
  path = find_in_parent_folders()
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules/snowflake/s3-storage-integration"
}

dependency "lz" {
  config_path = "../buttercup-lz"

  mock_outputs = {
    s3_bucket_arn  = "arn:aws:s3:::MOCK_BUTTERCUP_BUCKET"
    s3_bucket_name = "MOCK_BUTTERCUP_BUCKET"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "db" {
  config_path = "../buttercup-db"

  mock_outputs = {
    name = "MOCK_BUTTERCUP"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "db_arch" {
  config_path = "../buttercup-db-arch"

  mock_outputs = {
    landing_zone_schema_name = "MOCK_LANDING_ZONE"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  name            = "buttercup"
  s3_bucket_arn   = dependency.lz.outputs.s3_bucket_arn
  s3_bucket_name  = dependency.lz.outputs.s3_bucket_name
  s3_stage_prefix = "hot-confidential/7-days/aura-data-export"

  snowflake_database = dependency.db.outputs.name
  snowflake_schema   = dependency.db_arch.outputs.landing_zone_schema_name

  file_format_type = "JSON"
}
