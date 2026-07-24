"""add landing_zone_data_profiles table

Revision ID: c7e2a9f1d3b5
Revises: f4b8d2a6c1e9
Create Date: 2026-07-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e2a9f1d3b5'
down_revision = 'f4b8d2a6c1e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'landing_zone_data_profiles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('landing_zone_name', sa.String(length=255), nullable=False),
        sa.Column('file_format', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('expected_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('min_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('max_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('columns', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'landing_zone_name', name='uq_data_profile_account_lz'),
    )
    op.create_index(op.f('ix_landing_zone_data_profiles_account_id'), 'landing_zone_data_profiles', ['account_id'], unique=False)
    op.create_index(op.f('ix_landing_zone_data_profiles_landing_zone_name'), 'landing_zone_data_profiles', ['landing_zone_name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_landing_zone_data_profiles_landing_zone_name'), table_name='landing_zone_data_profiles')
    op.drop_index(op.f('ix_landing_zone_data_profiles_account_id'), table_name='landing_zone_data_profiles')
    op.drop_table('landing_zone_data_profiles')
