# Macros

## Conventions

- **Any timestamp column** — in any layer, on any model — should be typed through `standardize_timestamp()` rather than a bare cast. Keeps every timestamp in the project in the same `TIMESTAMP_NTZ`/UTC shape, so cross-model comparisons and joins on time never silently hit a timezone or precision mismatch.

## Schema naming

### `medallion_schema(layer)`
Resolves a medallion layer name (`bronze` / `silver` / `gold` / `platinum`) to the schema Terraform actually created for it: `upper("{layer}_{data_classification}")`, e.g. `SILVER_CONFIDENTIAL`. Mirrors `snowflake_schema.this` in `aws-snowflake//snowflake/medallion-arch`. The `data_classification` dbt var (set in `dbt_project.yml`) must match that module's `data_classification` input per environment, or this resolves a schema Terraform never created.

Use it directly whenever you need to reference a medallion schema by hand — e.g. building a fully-qualified table name in a run-operation or an ad hoc query.

### `generate_schema_name(custom_schema_name, node)`
Overrides dbt's built-in schema-name generation (the standard override point) so `{{ config(schema='silver') }}` on a model resolves through `medallion_schema()` instead of dbt's default `{{ target.schema }}_{{ custom_schema_name }}` concatenation. Only intercepts the four medallion layer names — any other custom schema falls through to dbt's stock behavior untouched.

You don't call this yourself. It runs automatically for every model; set `schema: bronze|silver|gold|platinum` in a model's config and it lands in the matching Terraform-created schema.

## Layer promotion (run-operations)

These rebuild a table in the next layer up from a supplied `SELECT`. All three are thin wrappers around `_promote_medallion_layer`, which resolves the target schema via `medallion_schema()` and does a `CREATE OR REPLACE TABLE ... AS SELECT` — a full rebuild, not incremental. Use them for one-off or scheduled promotions run outside the normal model DAG (e.g. via `dbt run-operation`), not as a replacement for modeling a table normally with `ref()`.

### `load_bronze_to_silver(target_table, select_sql, database=none)`
Bronze → Silver. `select_sql` typically unpacks a Bronze table's `RAW_DATA` VARIANT column (see `extract_json_field`) and dedupes/cleans it (see below).

### `load_silver_to_gold(target_table, select_sql, database=none)`
Silver → Gold. `select_sql` typically joins/aggregates one or more Silver tables into a business-facing shape.

### `load_gold_to_platinum(target_table, select_sql, database=none)`
Gold → Platinum. `select_sql` typically curates a Gold table for a specific consumer (a dashboard, an ML feature set, an external export).

### `_promote_medallion_layer(target_layer, target_table, select_sql, database=none)`
Internal — shared by the three macros above so schema resolution isn't duplicated three times. Not meant to be called directly; call one of the three named wrappers instead.

## Model-time helpers

Plain SQL-generating macros meant to be embedded inline in a model's `select`, not run standalone.

### `extract_json_field(column_name, path, type='string')`
Extracts a field from a VARIANT/JSON column and casts it, e.g. `extract_json_field('raw_data', 'customer.email')` → `raw_data:customer:email::string`. `path` is dot-separated for nested fields. Use it when unpacking Bronze's `RAW_DATA` into typed Silver columns.

### `dedupe(relation, partition_by, order_by)`
Wraps a `select * from {{ relation }}` with `QUALIFY ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1` to keep one row per key group. `partition_by` is often composite (a natural key plus an event timestamp) when the same logical record can be re-ingested more than once — `order_by` then just picks a tiebreaker among the copies. Use it as a CTE wherever a source can contain duplicate rows, typically in a Bronze → Silver model.

### `clean_string(column_name, null_values=[])`
Trims whitespace and normalizes blanks (and any upstream placeholder strings passed via `null_values`, e.g. `'N/A'`) to `NULL` for a single column expression. Use it in a `select` list wherever you're pulling a string column out of raw/messy source data.

### `standardize_timestamp(column_name, source_tz='UTC')`
Casts a raw timestamp column to a single common format: `TIMESTAMP_NTZ` normalized to UTC. `source_tz` tells it what timezone to interpret a naive (offset-less) raw value as before converting; any offset already embedded in the raw string is dropped in favor of `source_tz`. Use it in a `select` list wherever you're typing a raw timestamp column, most often unpacking Bronze's `RAW_DATA` alongside `extract_json_field`.

## Generic tests

Applied under a column's `tests:` list in a schema.yml, same as dbt's built-in `unique` / `not_null` / `accepted_values`.

### `accepted_range(min_value=none, max_value=none, inclusive=true)`
Fails rows where the column falls outside `[min_value, max_value]`. Either bound can be omitted to check only one side; `inclusive=false` makes the boundary values themselves fail. NULLs are never flagged — pair with `not_null` if they should be.

### `valid_email`
Fails non-null rows that don't match a basic `local@domain.tld` shape. A sanity check against obviously malformed values, not an RFC 5322-complete or mailbox-exists guarantee. NULLs are never flagged — pair with `not_null` if the column is required.
