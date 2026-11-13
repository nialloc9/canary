{% macro extract_json_field(column_name, path, type='string') %}
{#
    Extracts a field from a VARIANT/JSON column and casts it, for unpacking
    Bronze's RAW_DATA into typed Silver columns. `path` is dot-separated for
    nested fields (translated to Snowflake's colon VARIANT-path syntax).

    Usage:
        select
            {{ extract_json_field('raw_data', 'id', 'int') }} as order_id,
            {{ extract_json_field('raw_data', 'customer.email') }} as customer_email,
            {{ extract_json_field('raw_data', 'created_at', 'timestamp') }} as created_at
        from {{ source('bronze', 'orders') }}
#}
{%- set variant_path = path | replace('.', ':') -%}
{{ column_name }}:{{ variant_path }}::{{ type }}
{%- endmacro %}
