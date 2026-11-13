{% test valid_email(model, column_name) %}
{#
    Fails any row where `column_name` is non-null but doesn't match a basic
    email shape (local@domain.tld). Not RFC 5322-complete — it's a sanity
    check against obviously malformed values (missing @, no domain, no TLD),
    not a mailbox-exists guarantee. NULLs are not flagged — pair with a
    `not_null` test if the column is required.

    Usage (schema.yml):
        columns:
          - name: customer_email
            tests:
              - valid_email
#}

select *
from {{ model }}
where {{ column_name }} is not null
  and not regexp_like({{ column_name }}, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$')

{% endtest %}
