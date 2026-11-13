"""dev stack no longer default

"dev" was seeded with is_default=True for every account (auth.py) — that's
no longer the policy, so backfill existing accounts to match: no stack is
implicitly default, the user picks one explicitly each time.

Revision ID: e91a4c2f7b58
Revises: b2f7e4c9a103
Create Date: 2026-08-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e91a4c2f7b58'
down_revision = 'b2f7e4c9a103'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE stacks SET is_default = false WHERE name = 'dev' AND is_default = true"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE stacks SET is_default = true WHERE name = 'dev'"
    ))
