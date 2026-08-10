{% macro load_bronze_to_silver(target_table, select_sql, database=none) %}
{#
    Rebuilds `target_table` in the Silver schema (e.g. SILVER_CONFIDENTIAL,
    see medallion_schema()) from `select_sql` — typically a query against a
    Bronze table that unpacks RAW_DATA and applies dedupe()/clean_string().

    Usage:
        dbt run-operation load_bronze_to_silver --args '{
            "target_table": "ORDERS",
            "select_sql": "select raw_data:id::int as order_id, raw_data:updated_at::timestamp as updated_at from my_db.bronze_confidential.orders_bronze qualify row_number() over (partition by raw_data:id order by load_timestamp desc) = 1"
        }'
#}
{{ return(_promote_medallion_layer('silver', target_table, select_sql, database)) }}
{% endmacro %}
