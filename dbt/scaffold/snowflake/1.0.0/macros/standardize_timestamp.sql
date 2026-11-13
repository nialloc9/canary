{% macro standardize_timestamp(column_name, source_tz='UTC') %}
{#
    Casts a raw timestamp column to a single common format: TIMESTAMP_NTZ,
    normalized to UTC. Meant to be used inline in a select list, not as a
    standalone statement — pairs with extract_json_field() when unpacking a
    Bronze VARIANT column that holds a timestamp string.

    `source_tz` is the timezone the raw value is in when it's a naive
    value with no offset of its own (e.g. a '2024-01-15 09:30:00' string
    from a source system known to log in US/Eastern). Any offset already
    embedded in the raw string (e.g. a trailing '+05:00' or 'Z') is dropped
    in favor of `source_tz` — if a source mixes naive and offset-aware
    timestamps, handle it explicitly rather than relying on this macro.

    Usage:
        select
            {{ standardize_timestamp('raw_created_at') }} as created_at,
            {{ standardize_timestamp('raw_updated_at', source_tz='America/New_York') }} as updated_at
        from {{ ref('stg_orders') }}
#}
    convert_timezone('{{ source_tz }}', 'UTC', try_to_timestamp_ntz({{ column_name }}::string))
{% endmacro %}
