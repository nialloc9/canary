"""github flow: single trunk branch, account-level module_version

Moves away from the branch-per-stack / dev-prod-promotion model: every stack's
PRs now target the same trunk branch, held on GitHubRepo.branch (default
changes from 'develop' to 'main' going forward — existing accounts keep
whatever branch they already had configured, since force-changing it could
silently repoint PRs at a branch that doesn't exist or isn't what they
expect). Stack.branch is dropped entirely.

Terraform module_version also moves from per-stack to account/repo-level
(GitHubRepo.module_version), mirroring DbtRepo.scaffold_version — every stack
now vendors the same module version. Existing accounts are backfilled from
their lowest-sort_order stack's module_version (the same "stacks[0]" stack
tools already treated as representative when acting across multiple stacks
in one call).

Revision ID: b2f7e4c9a103
Revises: 4d8a1f6c9b27
Create Date: 2026-08-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2f7e4c9a103'
down_revision = '4d8a1f6c9b27'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'github_repos',
        sa.Column('module_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        UPDATE github_repos
        SET module_version = (
            SELECT s.module_version FROM stacks s
            WHERE s.account_id = github_repos.account_id
            ORDER BY s.sort_order ASC
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM stacks s WHERE s.account_id = github_repos.account_id
        )
        """
    ))

    op.alter_column('github_repos', 'branch', server_default='main')

    op.drop_column('stacks', 'module_version')
    op.drop_column('stacks', 'branch')


def downgrade() -> None:
    op.add_column(
        'stacks',
        sa.Column('branch', sa.String(length=255), nullable=False, server_default='main'),
    )
    op.add_column(
        'stacks',
        sa.Column('module_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        UPDATE stacks
        SET module_version = (
            SELECT g.module_version FROM github_repos g WHERE g.account_id = stacks.account_id
        )
        WHERE EXISTS (
            SELECT 1 FROM github_repos g WHERE g.account_id = stacks.account_id
        )
        """
    ))

    op.alter_column('github_repos', 'branch', server_default='develop')
    op.drop_column('github_repos', 'module_version')
