{% macro _quarantine_rows(source_table, schema, reason, select_sql, database=none) %}
{#
    Shared by quarantine() and validate_and_promote() so the
    create-if-not-exists + insert logic behind quarantining isn't duplicated
    between a caller that already has a bad-rows query in hand and one that
    still needs to run a test macro to get one. Not meant to be called
    directly — call quarantine() for a single check, or validate_and_promote()
    to run several checks and promote whatever passes all of them.

    The quarantine table is named QUARANTINE_<source_table> in the given
    schema, created on first use if it doesn't already exist. Its columns
    are fixed and generic regardless of what's being quarantined or which
    check caught it — the offending row is packed into RAW_DATA as a
    VARIANT via OBJECT_CONSTRUCT(*), so the same table shape works no
    matter which model or check produced it:

        quarantined_at   timestamp_ntz  -- when the row was quarantined (UTC)
        source_table     string         -- value passed in as `source_table`
        reason           string         -- why it was quarantined
        raw_data         variant        -- the full offending row, as-is

    Appends rather than replaces, so the quarantine table accumulates a
    history of rejected rows across runs instead of only reflecting the
    latest one.
#}
{% set db = database or target.database %}
{% set quarantine_table = 'QUARANTINE_' ~ source_table %}
{% set quarantine_relation_fqn = db ~ '.' ~ schema ~ '.' ~ quarantine_table %}

{% set create_sql %}
    create table if not exists {{ quarantine_relation_fqn }} (
        quarantined_at timestamp_ntz,
        source_table string,
        reason string,
        raw_data variant
    )
{% endset %}

{% set insert_sql %}
    insert into {{ quarantine_relation_fqn }} (quarantined_at, source_table, reason, raw_data)
    select
        convert_timezone('UTC', current_timestamp())::timestamp_ntz as quarantined_at,
        '{{ source_table }}' as source_table,
        '{{ reason }}' as reason,
        object_construct(*) as raw_data
    from (
        {{ select_sql }}
    ) as bad_rows
{% endset %}

{% if execute %}
    {% do run_query(create_sql) %}
    {% set results = run_query(insert_sql) %}
    {{ log("quarantined -> " ~ quarantine_relation_fqn, info=True) }}
    {{ return(results) }}
{% endif %}
{% endmacro %}


{% macro quarantine(source_table, schema, test_name, test_kwargs={}, database=none) %}
{#
    Runs a single generic test against `source_table` and appends whatever
    rows it finds failing into a quarantine table (see _quarantine_rows).
    Chains onto this scaffold's own generic tests (accepted_range,
    valid_email) or any other generic test macro, dbt's built-ins included
    (not_null, unique, accepted_values, relationships) — so a missing-data
    check is just `test_name: "not_null"`.

    `test_name` is a generic test's macro name without the `test_` prefix.
    `test_kwargs` is everything that test needs besides `model` — most
    commonly `column_name`, plus whatever else it takes (e.g. `min_value` /
    `max_value` for accepted_range).

    For running several checks against a batch at once and only promoting
    the rows that pass all of them, see validate_and_promote() below —
    that's the same idea as this macro, but as one step in a full
    check-then-load pipeline instead of quarantining in isolation.

    Usage:
        dbt run-operation quarantine --args '{
            "source_table": "ORDERS",
            "schema": "silver_confidential",
            "test_name": "accepted_range",
            "test_kwargs": {"column_name": "order_total", "min_value": 0}
        }'

        dbt run-operation quarantine --args '{
            "source_table": "CUSTOMERS",
            "schema": "silver_confidential",
            "test_name": "valid_email",
            "test_kwargs": {"column_name": "email"}
        }'

        dbt run-operation quarantine --args '{
            "source_table": "CUSTOMERS",
            "schema": "silver_confidential",
            "test_name": "not_null",
            "test_kwargs": {"column_name": "email"}
        }'
#}
{% set db = database or target.database %}
{% set relation = api.Relation.create(database=db, schema=schema, identifier=source_table) %}

{% set test_macro_name = 'test_' ~ test_name %}
{% if test_macro_name not in context %}
    {{ exceptions.raise_compiler_error("quarantine: no generic test macro named '" ~ test_macro_name ~ "' is available") }}
{% endif %}
{% set bad_rows_sql = context[test_macro_name](model=relation, **test_kwargs) %}

{% if execute %}
    {{ return(_quarantine_rows(source_table, schema, test_name, bad_rows_sql, database)) }}
{% endif %}
{% endmacro %}


{% macro validate_and_promote(target_layer, target_table, select_sql, checks=[], database=none) %}
{#
    The full check-then-load pipeline: runs every check in `checks` against
    the candidate rows from `select_sql`, quarantines whatever fails each
    one (via _quarantine_rows — same mechanism as quarantine()), and
    promotes only the rows that passed every check into `target_table` in
    `target_layer` (via _promote_medallion_layer — a full rebuild, same as
    load_bronze_to_silver / load_silver_to_gold / load_gold_to_platinum).

    `checks` is a list of `{test_name, test_kwargs}` objects — `test_name`
    is a generic test's macro name without the `test_` prefix
    (accepted_range, valid_email, or dbt's built-ins: not_null, unique,
    accepted_values, relationships); `test_kwargs` is whatever that test
    needs besides `model`, almost always `column_name`. Every failing row
    lands in QUARANTINE_<target_table> tagged with the check that caught
    it — a row failing more than one check is quarantined once per check.

    Works by first materializing `select_sql` into a temporary staging
    table tagged with a row hash, so every check runs against the exact
    same snapshot of candidate rows and a row can be identified
    consistently across checks without assuming a primary key. Each check
    then runs against that staging table, and whatever staging rows never
    matched a failing hash get promoted.

    Usage:
        dbt run-operation validate_and_promote --args '{
            "target_layer": "silver",
            "target_table": "CUSTOMERS",
            "select_sql": "select raw_data:id::int as customer_id, raw_data:email::string as email from my_db.bronze_confidential.customers_bronze qualify row_number() over (partition by raw_data:id order by load_timestamp desc) = 1",
            "checks": [
                {"test_name": "not_null", "test_kwargs": {"column_name": "email"}},
                {"test_name": "valid_email", "test_kwargs": {"column_name": "email"}}
            ]
        }'
#}
{% set db = database or target.database %}
{% set schema = medallion_schema(target_layer) %}
{% set staging_table = '_VALIDATE_' ~ target_table %}
{% set staging_relation_fqn = db ~ '.' ~ schema ~ '.' ~ staging_table %}
{% set staging_relation = api.Relation.create(database=db, schema=schema, identifier=staging_table) %}

{% set stage_sql %}
    create or replace temporary table {{ staging_relation_fqn }} as
    select *, md5(to_varchar(object_construct(*))) as _quarantine_row_hash
    from (
        {{ select_sql }}
    ) as candidate
{% endset %}

{% if execute %}
    {% do run_query(stage_sql) %}

    {% set bad_hash_selects = [] %}
    {% for check in checks %}
        {% set test_macro_name = 'test_' ~ check['test_name'] %}
        {% if test_macro_name not in context %}
            {{ exceptions.raise_compiler_error("validate_and_promote: no generic test macro named '" ~ test_macro_name ~ "' is available") }}
        {% endif %}
        {% set bad_rows_sql = context[test_macro_name](model=staging_relation, **check.get('test_kwargs', {})) %}
        {% do _quarantine_rows(target_table, schema, check['test_name'], bad_rows_sql, database) %}
        {% do bad_hash_selects.append('select _quarantine_row_hash from (' ~ bad_rows_sql ~ ') as bad_' ~ loop.index) %}
    {% endfor %}

    {% set good_rows_sql %}
        select * exclude (_quarantine_row_hash)
        from {{ staging_relation_fqn }}
        {%- if bad_hash_selects %}
        where _quarantine_row_hash not in (
            {{ bad_hash_selects | join('\n            union all\n            ') }}
        )
        {%- endif %}
    {% endset %}

    {% set results = _promote_medallion_layer(target_layer, target_table, good_rows_sql, database) %}
    {% do run_query('drop table if exists ' ~ staging_relation_fqn) %}
    {{ return(results) }}
{% endif %}
{% endmacro %}
