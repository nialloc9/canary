"""add data_classifications table and project default_retention_policy

Revision ID: 4d8a1f6c9b27
Revises: 9b3f6a2c7e14
Create Date: 2026-08-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '4d8a1f6c9b27'
down_revision = '9b3f6a2c7e14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'data_classifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'name', name='uq_data_classification_account_name'),
    )
    op.create_index(
        op.f('ix_data_classifications_account_id'), 'data_classifications', ['account_id'], unique=False
    )
    op.add_column('projects', sa.Column('default_retention_policy', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'default_retention_policy')
    op.drop_index(op.f('ix_data_classifications_account_id'), table_name='data_classifications')
    op.drop_table('data_classifications')
