{% macro clean_string(column_name, null_values=[]) %}
{#
    Trims whitespace and normalizes blank/placeholder values to NULL for a
    single column expression. Meant to be used inline in a select list, not
    as a standalone statement.

    `null_values` catches upstream placeholder strings (e.g. 'N/A', 'NULL',
    'none') that should be treated as missing data rather than literal text.

    Usage:
        select
            {{ clean_string('customer_name') }} as customer_name,
            {{ clean_string('country_code', null_values=['N/A', 'UNKNOWN']) }} as country_code
        from {{ ref('stg_customers') }}
#}
{%- if null_values %}
    case
        when trim({{ column_name }}) in ({{ "'" ~ null_values | join("', '") ~ "'" }}) then null
        else nullif(trim({{ column_name }}), '')
    end
{%- else %}
    nullif(trim({{ column_name }}), '')
{%- endif -%}
{% endmacro %}
