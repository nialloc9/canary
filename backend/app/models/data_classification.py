import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataClassification(Base):
    """Account-managed list of data classification values (e.g. "confidential")
    landing zones/tables get tagged with — unlike retention_policy (a fixed
    enum with day-count math baked into _lifecycle_days), classification is
    pure taxonomy with no behavior tied to specific values, so accounts can
    define their own instead of being stuck with a hardcoded set.

    description exists so the agent (and the admin managing this list) has
    something to judge fit against — e.g. deciding whether a table with an
    inferred email column looks more sensitive than the configured default.
    At most one row per account should have is_default=True; enforcing that
    is application-level (see data_classifications route), not a DB
    constraint, since briefly having zero defaults mid-update is fine.
    """

    __tablename__ = "data_classifications"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_data_classification_account_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
