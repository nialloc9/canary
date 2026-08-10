{% macro load_silver_to_gold(target_table, select_sql, database=none) %}
{#
    Rebuilds `target_table` in the Gold schema (e.g. GOLD_CONFIDENTIAL, see
    medallion_schema()) from `select_sql` — typically a query against one or
    more Silver tables that joins/aggregates into a business-facing shape.

    Usage:
        dbt run-operation load_silver_to_gold --args '{
            "target_table": "DAILY_ORDER_SUMMARY",
            "select_sql": "select order_date, count(*) as order_count from my_db.silver_confidential.orders group by 1"
        }'
#}
{{ return(_promote_medallion_layer('gold', target_table, select_sql, database)) }}
{% endmacro %}
