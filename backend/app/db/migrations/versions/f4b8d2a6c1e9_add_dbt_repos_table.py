"""add dbt_repos table

Revision ID: f4b8d2a6c1e9
Revises: a1c3e7f9b2d4
Create Date: 2026-07-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f4b8d2a6c1e9'
down_revision = 'a1c3e7f9b2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dbt_repos',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('repo_full_name', sa.String(length=255), nullable=False),
        sa.Column('branch', sa.String(length=255), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('api_url', sa.String(length=512), nullable=False),
        sa.Column('dbt_base_path', sa.String(length=512), nullable=False),
        sa.Column('cicd_provider', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', name='uq_dbt_repo_account'),
    )
    op.create_index(op.f('ix_dbt_repos_account_id'), 'dbt_repos', ['account_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dbt_repos_account_id'), table_name='dbt_repos')
    op.drop_table('dbt_repos')
