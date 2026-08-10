{% macro dedupe(relation, partition_by, order_by) %}
{#
    Drops duplicate rows from `relation`, keeping one row per `partition_by`
    group ranked by `order_by`. Uses QUALIFY (Snowflake-specific) instead of
    a wrapping subquery so it can be embedded straight into a CTE.

    `partition_by` is often composite (e.g. a natural key plus an event
    timestamp) when the same logical record can be re-ingested more than
    once — `order_by` then just picks a tiebreaker among the copies.

    Usage:
        with deduped as (
            {{ dedupe(
                ref('stg_orders'),
                partition_by='order_id, event_timestamp',
                order_by='updated_at desc'
            ) }}
        )
        select * from deduped
#}
    select *
    from {{ relation }}
    qualify row_number() over (
        partition by {{ partition_by }}
        order by {{ order_by }}
    ) = 1
{% endmacro %}
