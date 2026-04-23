import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.campaign import CampaignStatus, MediaType


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    segment_id: uuid.UUID | None = None
    message_template: str = Field(..., min_length=1)
    media_url: str | None = None
    media_type: MediaType | None = None
    scheduled_at: datetime | None = None
    lead_group: str | None = None
    allowed_instances: list[str] | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    segment_id: uuid.UUID | None = None
    message_template: str | None = None
    media_url: str | None = None
    media_type: MediaType | None = None
    scheduled_at: datetime | None = None
    lead_group: str | None = None
    allowed_instances: list[str] | None = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID
    segment_id: uuid.UUID | None
    message_template: str
    media_url: str | None
    media_type: MediaType | None
    status: CampaignStatus
    lead_group: str | None
    allowed_instances: list[str] | None
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    total_leads: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CampaignResponse]
