import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SegmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    filters: dict = Field(default_factory=dict)


class SegmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    filters: dict | None = None


class SegmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    filters: dict
    lead_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
