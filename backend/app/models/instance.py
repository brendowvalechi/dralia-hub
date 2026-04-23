import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstanceStatus(str, PyEnum):
    connected = "connected"
    disconnected = "disconnected"
    warming_up = "warming_up"
    banned = "banned"
    quarantine = "quarantine"


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    evolution_instance_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    status: Mapped[InstanceStatus] = mapped_column(
        Enum(InstanceStatus, name="instancestatus"),
        nullable=False,
        default=InstanceStatus.disconnected,
        index=True,
    )
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    daily_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warmup_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ban_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
