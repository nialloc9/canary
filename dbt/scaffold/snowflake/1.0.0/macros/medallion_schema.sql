{% macro medallion_schema(layer) %}
{#
    Resolves the schema name for a medallion layer the same way Terraform
    does (snowflake_schema.this in aws-snowflake//snowflake/medallion-arch):

        upper("${layer}_${data_classification}")

    e.g. layer='silver' -> SILVER_CONFIDENTIAL. The `data_classification`
    dbt var must be kept in sync with that module's `data_classification`
    input per environment, or dbt will resolve a schema Terraform never
    created.
#}
{{ return((layer ~ '_' ~ var('data_classification', 'confidential')) | upper) }}
{% endmacro %}
