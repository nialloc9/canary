import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

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
