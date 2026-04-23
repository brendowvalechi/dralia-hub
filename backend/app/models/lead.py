import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LeadSource(str, PyEnum):
    import_ = "import"
    manual = "manual"
    api = "api"
    webhook = "webhook"


class LeadStatus(str, PyEnum):
    active = "active"
    inactive = "inactive"
    opted_out = "opted_out"
    blacklisted = "blacklisted"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    custom_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[LeadSource] = mapped_column(
        Enum(LeadSource, name="leadsource"), nullable=False, default=LeadSource.manual
    )
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="leadstatus"),
        nullable=False,
        default=LeadStatus.active,
        index=True,
    )
    opt_in_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opt_out_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_record: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_leads_tags", tags, postgresql_using="gin"),
    )
