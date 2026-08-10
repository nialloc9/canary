{% macro generate_schema_name(custom_schema_name, node) -%}
{#
    Overrides dbt's built-in schema-name generation (the standard override
    point — see https://docs.getdbt.com/docs/build/custom-schemas) so that
    {{ config(schema='silver') }} etc. resolves through medallion_schema()
    and lands in the same schema Terraform already created (e.g.
    SILVER_CONFIDENTIAL), instead of dbt's default
    "{{ target.schema }}_{{ custom_schema_name }}" concatenation.

    Only intercepts the four medallion layer names; any other custom schema
    falls back to dbt's stock behavior untouched.
#}
{%- set medallion_layers = ['bronze', 'silver', 'gold', 'platinum'] -%}
{%- if custom_schema_name is not none and custom_schema_name | lower in medallion_layers -%}
    {{ medallion_schema(custom_schema_name | lower) }}
{%- else -%}
    {{ default__generate_schema_name(custom_schema_name, node) }}
{%- endif -%}
{%- endmacro %}
