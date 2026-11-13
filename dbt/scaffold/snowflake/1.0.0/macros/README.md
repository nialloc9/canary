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

## Quarantine & validation (run-operations)

Together these are the generic check-then-load pipeline: run a check against candidate rows, quarantine what fails, promote what doesn't. `quarantine` does the first two steps standalone; `validate_and_promote` chains all three so bad rows never reach the target table in the first place.

### `_quarantine_rows(source_table, schema, reason, select_sql, database=none)`
Internal — shared by `quarantine` and `validate_and_promote` so the create-if-not-exists + insert logic isn't duplicated. Not meant to be called directly.

Creates `QUARANTINE_<source_table>` in the given schema on first use, then appends `select_sql`'s rows to it. Columns are fixed and generic regardless of what's being quarantined or which check caught it: `quarantined_at` (UTC), `source_table`, `reason`, and `raw_data` — the full offending row packed into a VARIANT via `OBJECT_CONSTRUCT(*)`, so the same table shape works for any model. Appends rather than replaces, so it accumulates a history of rejected rows across runs.

### `quarantine(source_table, schema, test_name, test_kwargs={}, database=none)`
Runs a single generic test against `source_table` and quarantines whatever rows it finds failing (via `_quarantine_rows`).

It works by calling the test macro (`test_<test_name>`, e.g. `test_valid_email` or `test_accepted_range`) directly to get the failing-rows query, then inserting the result. `test_name` is the generic test's name without the `test_` prefix; `test_kwargs` is whatever that test needs besides `model` — usually `column_name`, plus anything test-specific (`min_value`/`max_value` for `accepted_range`). Works with this scaffold's own generic tests (`accepted_range`, `valid_email`) and dbt's built-ins (`not_null`, `unique`, `accepted_values`, `relationships`) alike — a missing-data check is just `test_name: "not_null"`.

Usage — quarantine customers with an invalid email:
```
dbt run-operation quarantine --args '{
    "source_table": "CUSTOMERS",
    "schema": "silver_confidential",
    "test_name": "valid_email",
    "test_kwargs": {"column_name": "email"}
}'
```

Usage — quarantine orders with a negative total:
```
dbt run-operation quarantine --args '{
    "source_table": "ORDERS",
    "schema": "silver_confidential",
    "test_name": "accepted_range",
    "test_kwargs": {"column_name": "order_total", "min_value": 0}
}'
```

Usage — quarantine rows with a missing (null) required column:
```
dbt run-operation quarantine --args '{
    "source_table": "CUSTOMERS",
    "schema": "silver_confidential",
    "test_name": "not_null",
    "test_kwargs": {"column_name": "email"}
}'
```

### `validate_and_promote(target_layer, target_table, select_sql, checks=[], database=none)`
The full pipeline: runs every check in `checks` against the candidate rows from `select_sql`, quarantines whatever fails each one, and promotes only the rows that passed every check into `target_table` in `target_layer` (via `_promote_medallion_layer` — a full rebuild, same as `load_bronze_to_silver` / `load_silver_to_gold` / `load_gold_to_platinum`).

`checks` is a list of `{test_name, test_kwargs}` objects, same shape as `quarantine`'s arguments. Every failing row lands in `QUARANTINE_<target_table>` tagged with the check that caught it — a row failing more than one check is quarantined once per check, and never reaches `target_table` either way.

Under the hood it first materializes `select_sql` into a temporary staging table tagged with a row hash, so every check runs against the exact same snapshot of candidate rows and a row can be identified consistently across checks without assuming a primary key.

Usage — load Bronze customers into Silver, quarantining any with a missing or invalid email instead of promoting them:
```
dbt run-operation validate_and_promote --args '{
    "target_layer": "silver",
    "target_table": "CUSTOMERS",
    "select_sql": "select raw_data:id::int as customer_id, raw_data:email::string as email from my_db.bronze_confidential.customers_bronze qualify row_number() over (partition by raw_data:id order by load_timestamp desc) = 1",
    "checks": [
        {"test_name": "not_null", "test_kwargs": {"column_name": "email"}},
        {"test_name": "valid_email", "test_kwargs": {"column_name": "email"}}
    ]
}'
```

## Generic tests

Applied under a column's `tests:` list in a schema.yml, same as dbt's built-in `unique` / `not_null` / `accepted_values`.

### `accepted_range(min_value=none, max_value=none, inclusive=true)`
Fails rows where the column falls outside `[min_value, max_value]`. Either bound can be omitted to check only one side; `inclusive=false` makes the boundary values themselves fail. NULLs are never flagged — pair with `not_null` if they should be.

### `valid_email`
Fails non-null rows that don't match a basic `local@domain.tld` shape. A sanity check against obviously malformed values, not an RFC 5322-complete or mailbox-exists guarantee. NULLs are never flagged — pair with `not_null` if the column is required.
