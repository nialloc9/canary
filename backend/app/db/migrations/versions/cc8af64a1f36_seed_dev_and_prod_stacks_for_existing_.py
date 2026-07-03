"""seed dev and prod stacks for existing accounts

Every account needs a "dev" (tracks develop) and "prod" (tracks main) stack —
the release flow resolves them by name. New accounts get both at registration;
this backfills existing ones:
  - the pre-existing default stack tracking the "main" branch is renamed to "prod"
  - a new "dev" stack (branch=develop) is added if the account doesn't have one

Revision ID: cc8af64a1f36
Revises: 2b0156eda598
Create Date: 2026-07-01 22:01:45.107523
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = 'cc8af64a1f36'
down_revision = '2b0156eda598'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Rename each account's pre-existing default/main-branch stack to "prod",
    # demoting is_default (dev becomes the new default below).
    conn.execute(sa.text(
        "UPDATE stacks SET name = 'prod', is_default = false "
        "WHERE branch = 'main' AND name != 'prod'"
    ))

    accounts = conn.execute(sa.text("SELECT id FROM accounts")).fetchall()
    for (account_id,) in accounts:
        has_dev = conn.execute(
            sa.text("SELECT 1 FROM stacks WHERE account_id = :aid AND name = 'dev'"),
            {"aid": account_id},
        ).first()
        if has_dev:
            continue

        # Free up sort_order 0 for the new "dev" stack. Offset by a large constant
        # (not +1) so a multi-row shift can't transiently collide with a not-yet-updated
        # sibling row's current value under the unique(account_id, sort_order) constraint.
        conn.execute(
            sa.text("UPDATE stacks SET sort_order = sort_order + 1000 WHERE account_id = :aid"),
            {"aid": account_id},
        )

        now = datetime.now(timezone.utc)
        conn.execute(
            sa.text(
                "INSERT INTO stacks (id, account_id, name, branch, verify_before_pr, "
                "verify_max_attempts, sort_order, is_default, type, sf_authenticator, "
                "cloud_provider, cloud_region, created_at, updated_at) "
                "VALUES (:id, :aid, 'dev', 'develop', false, 3, 0, true, 'snowflake', "
                "'SNOWFLAKE_JWT', 'aws', 'us-east-1', :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "aid": account_id, "now": now},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM stacks WHERE name = 'dev'"))
    conn.execute(sa.text("UPDATE stacks SET name = 'main', is_default = true WHERE name = 'prod'"))
