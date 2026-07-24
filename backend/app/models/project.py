import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    """One project per account — an account's single software delivery pipeline
    (one GitHub repo, one CI/CD setup) that deploys to all of the account's stacks."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("account_id", name="uq_project_account"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version_control_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cicd_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    infrastructure_bootstrapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CiCd(Base):
    __tablename__ = "cicd"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    github_repo_id: Mapped[str] = mapped_column(ForeignKey("github_repos.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    bootstrapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class GitHubRepo(Base):
    """One connected repo per account, matching the one-project-per-account rule."""

    __tablename__ = "github_repos"
    __table_args__ = (UniqueConstraint("account_id", name="uq_github_repo_account"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="develop")
    token: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[str] = mapped_column(String(512), nullable=False, default="https://api.github.com")
    infrastructure_base_path: Mapped[str] = mapped_column(String(512), nullable=False, default="infrastructure")
    auto_merge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    create_cicd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # "github_actions" or "circleci". github_actions gets secret *values*
    # pushed via the GitHub API into per-stack-suffixed repo secrets.
    # circleci never receives secret values from Canary at all — it only
    # references a context name (Stack.circleci_context) that the user must
    # have already populated themselves in CircleCI's own project settings.
    cicd_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="github_actions")
    skip_bootstrap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skip_module_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DbtRepo(Base):
    """One connected dbt repo per account — deliberately separate from
    GitHubRepo (the infra repo) rather than a shared table with a "purpose"
    column: infra and dbt have different reviewers, different CI toolchains,
    and change at very different cadences, and every existing tool/route
    already assumes exactly one GitHubRepo per account. Keeping this as its
    own table means none of that existing code has to be touched, and a
    dbt-side mistake can't accidentally read/write the infra repo or vice
    versa. No auto_merge field: dbt PRs are never auto-merged, deliberately,
    since a silently-wrong data model is worse than a silently-wrong infra
    resource — that isn't meant to be user-configurable yet."""

    __tablename__ = "dbt_repos"
    __table_args__ = (UniqueConstraint("account_id", name="uq_dbt_repo_account"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    token: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[str] = mapped_column(String(512), nullable=False, default="https://api.github.com")
    # "." (repo root) by default — dbt's own ecosystem (dbt Cloud, dbt Docs,
    # editor tooling) generally assumes the project lives at repo root, so
    # this is only here for the rare case someone wants it nested.
    dbt_base_path: Mapped[str] = mapped_column(String(512), nullable=False, default=".")
    cicd_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="github_actions")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
