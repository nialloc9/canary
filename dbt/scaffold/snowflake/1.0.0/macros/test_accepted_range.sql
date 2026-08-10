{% test accepted_range(model, column_name, min_value=none, max_value=none, inclusive=true) %}
{#
    Fails any row where `column_name` falls outside [min_value, max_value].
    Either bound can be omitted to only check one side. `inclusive` (default
    true) controls whether the boundary values themselves pass. Rows where
    `column_name` is NULL are not flagged — pair with a `not_null` test if
    NULLs should fail too.

    Usage (schema.yml):
        columns:
          - name: discount_pct
            tests:
              - accepted_range:
                  min_value: 0
                  max_value: 100
              - accepted_range:
                  min_value: 0
                  inclusive: false
#}

{%- set min_operator = '>=' if inclusive else '>' -%}
{%- set max_operator = '<=' if inclusive else '<' -%}

select *
from {{ model }}
where 1=1
{%- if min_value is not none %}
    and not ({{ column_name }} {{ min_operator }} {{ min_value }})
{%- endif %}
{%- if max_value is not none %}
    and not ({{ column_name }} {{ max_operator }} {{ max_value }})
{%- endif %}

{% endtest %}
