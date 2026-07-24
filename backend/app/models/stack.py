import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Stack(Base):
    __tablename__ = "stacks"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_stack_account_name"),
        UniqueConstraint("account_id", "sort_order", name="uq_stack_account_sort_order"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    verify_before_pr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verify_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    module_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="snowflake")
    sf_organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_authenticator: Mapped[str] = mapped_column(String(50), nullable=False, default="SNOWFLAKE_JWT")
    sf_private_key_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    sf_database: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_warehouse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloud_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="aws")
    cloud_access_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloud_secret_access_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloud_region: Mapped[str | None] = mapped_column(String(50), nullable=True, default="us-east-1")
    # Only meaningful when the project's cicd_provider is "circleci" — the
    # name of a CircleCI context (created by the user in Project Settings →
    # Contexts, holding this stack's SNOWFLAKE_*/AWS_* env vars) that the
    # generated workflow's jobs for this stack will reference. Canary never
    # pushes secret values into it, unlike GitHub Actions repo secrets.
    circleci_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StackStateBackend(Base):
    __tablename__ = "stack_state_backends"
    __table_args__ = (
        UniqueConstraint("github_repo_id", "stack_id", name="uq_state_backend_repo_stack"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    github_repo_id: Mapped[str] = mapped_column(ForeignKey("github_repos.id"), nullable=False, index=True)
    stack_id: Mapped[str] = mapped_column(ForeignKey("stacks.id"), nullable=False, index=True)
    state_bucket: Mapped[str] = mapped_column(String(512), nullable=False)
    state_region: Mapped[str] = mapped_column(String(50), nullable=False)
    state_lock_table: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
