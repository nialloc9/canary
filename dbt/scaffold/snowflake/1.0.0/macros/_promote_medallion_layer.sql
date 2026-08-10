{% macro _promote_medallion_layer(target_layer, target_table, select_sql, database=none) %}
{#
    Shared by load_bronze_to_silver / load_silver_to_gold / load_gold_to_platinum
    so the schema-resolution logic isn't duplicated three times. Rebuilds
    `target_table` in the target layer's schema (resolved via
    medallion_schema() to match Terraform's naming) as a CREATE OR REPLACE
    TABLE AS SELECT — a full rebuild, not incremental.
#}
{% set db = database or target.database %}
{% set schema = medallion_schema(target_layer) %}
{% set target_relation_fqn = db ~ '.' ~ schema ~ '.' ~ target_table %}

{% set create_sql %}
    create or replace table {{ target_relation_fqn }} as
    {{ select_sql }}
{% endset %}

{% if execute %}
    {% set results = run_query(create_sql) %}
    {{ log("promoted -> " ~ target_relation_fqn, info=True) }}
    {{ return(results) }}
{% endif %}
{% endmacro %}
