"""add cicd_provider and circleci_context

Revision ID: a1c3e7f9b2d4
Revises: e32e69c1a218
Create Date: 2026-07-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c3e7f9b2d4'
down_revision = 'e32e69c1a218'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'github_repos',
        sa.Column('cicd_provider', sa.String(length=50), nullable=False, server_default='github_actions'),
    )
    op.add_column('stacks', sa.Column('circleci_context', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('stacks', 'circleci_context')
    op.drop_column('github_repos', 'cicd_provider')
