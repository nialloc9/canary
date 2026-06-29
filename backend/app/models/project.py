import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SnowflakeCredentials(Base):
    __tablename__ = "snowflake_credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user: Mapped[str] = mapped_column(String(255), nullable=False)
    authenticator: Mapped[str] = mapped_column(String(50), nullable=False, default="SNOWFLAKE_JWT")
    private_key_b64: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version_control_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cicd_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warehouse_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    infrastructure_bootstrapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    warehouse_credentials_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
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
    __tablename__ = "github_repos"

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
    dev_state_bucket: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dev_state_region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dev_state_lock_table: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prod_state_bucket: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prod_state_region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prod_state_lock_table: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
