import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.lead import LeadSource, LeadStatus


class LeadCreate(BaseModel):
    phone: str
    name: str | None = None
    email: str | None = None
    tags: list[str] = []
    custom_fields: dict[str, Any] = {}
    source: LeadSource = LeadSource.manual
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def phone_e164(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Telefone deve estar no formato E.164 (ex: +5511999999999)")
        digits = v[1:]
        if not digits.isdigit() or not (7 <= len(digits) <= 15):
            raise ValueError("Telefone inválido")
        return v


class LeadUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    tags: list[str] | None = None
    custom_fields: dict[str, Any] | None = None
    status: LeadStatus | None = None
    notes: str | None = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    phone: str
    name: str | None
    email: str | None
    tags: list[str]
    custom_fields: dict[str, Any]
    source: LeadSource
    status: LeadStatus
    opt_in_date: datetime | None
    opt_out_date: datetime | None
    consent_record: dict[str, Any] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[LeadResponse]


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
