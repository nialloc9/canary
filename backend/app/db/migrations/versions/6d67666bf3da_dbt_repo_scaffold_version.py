"""dbt repo: drop cicd_provider, add scaffold_version

Revision ID: 6d67666bf3da
Revises: c7e2a9f1d3b5
Create Date: 2026-07-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '6d67666bf3da'
down_revision = 'c7e2a9f1d3b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('dbt_repos', 'cicd_provider')
    op.add_column('dbt_repos', sa.Column('scaffold_version', sa.String(length=20), nullable=False, server_default='1.0.0'))


def downgrade() -> None:
    op.drop_column('dbt_repos', 'scaffold_version')
    op.add_column('dbt_repos', sa.Column('cicd_provider', sa.String(length=50), nullable=False, server_default='github_actions'))
