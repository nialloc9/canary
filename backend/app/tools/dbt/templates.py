import re

# Snowflake SQL cast type for each of the coarse type names the data-profile
# inference (app/services/data_profile_service.py) produces. Falls back to
# VARCHAR for anything unrecognized rather than failing — a wrong cast is
# easy to fix by hand in review, a missing column is not.
_SNOWFLAKE_TYPE = {
    "string": "VARCHAR", "text": "VARCHAR",
    "integer": "NUMBER", "int": "NUMBER",
    "float": "FLOAT", "number": "FLOAT", "decimal": "FLOAT",
    "boolean": "BOOLEAN", "bool": "BOOLEAN",
    "timestamp": "TIMESTAMP_NTZ", "datetime": "TIMESTAMP_NTZ",
    "date": "DATE",
    "array": "ARRAY",
    "object": "VARIANT",
}


def snowflake_cast_type(profile_type: str | None) -> str:
    return _SNOWFLAKE_TYPE.get((profile_type or "").lower(), "VARCHAR")


def sanitize_identifier(name: str) -> str:
    """dbt project names and model names must be valid identifiers — no
    hyphens, no leading digits."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower()
    if not cleaned:
        cleaned = "project"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _yaml_str(value: str) -> str:
    """Double-quoted YAML scalar, safe for arbitrary text: escape backslashes
    and double quotes, and flatten newlines (descriptions are meant to be
    short, and a raw newline inside a quoted YAML scalar is invalid)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


def dbt_project_yml(project_name: str) -> str:
    """Generated once, only if the target repo doesn't already have one (see
    CreateDbtStagingModelTool). persist_docs at the project level — rather
    than repeated per-model — is what makes `dbt run` push every model's and
    every column's `description` into Snowflake as native COMMENT metadata;
    without it, descriptions stay inert text living only in this repo.
    """
    name = sanitize_identifier(project_name)
    return f'''name: {_yaml_str(name)}
version: "1.0.0"
config-version: 2
profile: {_yaml_str(name)}

model-paths: ["models"]
macro-paths: ["macros"]

models:
  {name}:
    +persist_docs:
      relation: true
      columns: true
'''


def staging_model_sql(
    bronze_database: str,
    bronze_schema: str,
    bronze_table_name: str,
    columns: list[dict],
) -> str:
    column_lines = ",\n".join(
        f"    raw_data:{c['name']}::{snowflake_cast_type(c.get('type'))} as {c['name']}"
        for c in columns
    )
    return f'''-- Extracted from the Bronze table's RAW_DATA VARIANT column. Column list and
-- types come from the data profile captured when this landing zone was created
-- (see LandingZoneDataProfile) — re-run create_landing_zone's inference, or edit
-- this file directly, if the real payload shape has since changed.

select
{column_lines},
    source_file,
    load_timestamp
from {bronze_database}.{bronze_schema}.{bronze_table_name}
'''


def staging_model_schema_yml(
    model_name: str,
    description: str | None,
    columns: list[dict],
) -> str:
    column_blocks = "\n".join(
        f'      - name: {c["name"]}\n        description: {_yaml_str(c.get("description") or "")}'
        for c in columns
    )
    passthrough_blocks = (
        '      - name: source_file\n        description: "S3 key of the file this row was loaded from."\n'
        '      - name: load_timestamp\n        description: "When Snowpipe loaded this row."'
    )
    return f'''version: 2

models:
  - name: {model_name}
    description: {_yaml_str(description or "")}
    columns:
{column_blocks}
{passthrough_blocks}
'''
