{% macro load_gold_to_platinum(target_table, select_sql, database=none) %}
{#
    Rebuilds `target_table` in the Platinum schema (e.g. PLATINUM_CONFIDENTIAL,
    see medallion_schema()) from `select_sql` — typically a query against one
    or more Gold tables curated for a specific consumer (a dashboard, an ML
    feature set, an external export).

    Usage:
        dbt run-operation load_gold_to_platinum --args '{
            "target_table": "EXEC_DASHBOARD_METRICS",
            "select_sql": "select * from my_db.gold_confidential.daily_order_summary where order_date >= dateadd(day, -90, current_date())"
        }'
#}
{{ return(_promote_medallion_layer('platinum', target_table, select_sql, database)) }}
{% endmacro %}
