import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, BigInteger, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LandingZoneDataProfile(Base):
    """What's actually landing in a landing zone's Bronze table — collected once,
    at landing-zone creation time, so the (future) dbt-model-generation tool
    never has to ask the user for the same description/samples/columns twice.

    file_format/description/size stats/columns are all nullable: anything the
    user doesn't supply explicitly gets inferred from the sample file(s) they
    provide (see data_profile_service.infer_profile) rather than being
    required up front. Raw sample content itself is deliberately NOT stored
    here — only what was derived from it — to avoid holding onto arbitrary
    customer data at rest longer than the single inference call needs it.
    """

    __tablename__ = "landing_zone_data_profiles"
    __table_args__ = (
        UniqueConstraint("account_id", "landing_zone_name", name="uq_data_profile_account_lz"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    landing_zone_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # list of {"name": str, "type": str, "description": str | None, "example": str | None}
    columns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
