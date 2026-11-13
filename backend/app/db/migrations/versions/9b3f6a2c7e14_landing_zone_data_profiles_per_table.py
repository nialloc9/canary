"""landing_zone_data_profiles: one row per table

Revision ID: 9b3f6a2c7e14
Revises: 6d67666bf3da
Create Date: 2026-08-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '9b3f6a2c7e14'
down_revision = '6d67666bf3da'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('landing_zone_data_profiles', sa.Column('table_name', sa.String(length=255), nullable=True))
    op.add_column('landing_zone_data_profiles', sa.Column('owner', sa.String(length=255), nullable=True))
    op.add_column('landing_zone_data_profiles', sa.Column('refresh_rate', sa.String(length=100), nullable=True))
    op.add_column('landing_zone_data_profiles', sa.Column('data_classification', sa.String(length=50), nullable=True))
    op.add_column('landing_zone_data_profiles', sa.Column('s3_prefix', sa.String(length=1024), nullable=True))
    op.drop_constraint('uq_data_profile_account_lz', 'landing_zone_data_profiles', type_='unique')
    op.create_unique_constraint(
        'uq_data_profile_account_lz_table',
        'landing_zone_data_profiles',
        ['account_id', 'landing_zone_name', 'table_name'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_data_profile_account_lz_table', 'landing_zone_data_profiles', type_='unique')
    op.create_unique_constraint(
        'uq_data_profile_account_lz', 'landing_zone_data_profiles', ['account_id', 'landing_zone_name']
    )
    op.drop_column('landing_zone_data_profiles', 's3_prefix')
    op.drop_column('landing_zone_data_profiles', 'data_classification')
    op.drop_column('landing_zone_data_profiles', 'refresh_rate')
    op.drop_column('landing_zone_data_profiles', 'owner')
    op.drop_column('landing_zone_data_profiles', 'table_name')
