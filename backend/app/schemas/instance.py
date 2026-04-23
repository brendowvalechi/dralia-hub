import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.instance import InstanceStatus


class InstanceCreate(BaseModel):
    display_name: str
    evolution_instance_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Nome único na Evolution API (só letras, números, _ e -)",
    )
    daily_limit: int = Field(50, ge=1, le=1000)
    webhook_url: str | None = None


class InstanceUpdate(BaseModel):
    display_name: str | None = None
    daily_limit: int | None = Field(None, ge=1, le=1000)
    status: InstanceStatus | None = None


class InstanceResponse(BaseModel):
    id: uuid.UUID
    phone_number: str | None
    display_name: str
    evolution_instance_name: str
    status: InstanceStatus
    health_score: int
    daily_limit: int
    daily_sent: int
    warmup_day: int | None
    ban_count: int
    last_connected_at: datetime | None
    last_disconnected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InstanceQRCode(BaseModel):
    instance_name: str
    qrcode: str | None = None
    status: str
