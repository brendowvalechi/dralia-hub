"""
Segments API — gerenciamento de segmentos de leads para campanhas direcionadas.

Filtros suportados no JSONB:
  { "tags": ["vip", "sp"], "status": "active" }
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_operator
from app.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.segment import Segment
from app.models.user import User
from app.schemas.segment import SegmentCreate, SegmentResponse, SegmentUpdate

router = APIRouter(prefix="/segments", tags=["segments"])


async def _count_leads_for_filters(db: AsyncSession, filters: dict) -> int:
    """Conta leads que correspondem aos filtros do segmento."""
    q = select(func.count(Lead.id))

    # Filtro por status (padrão: active)
    seg_status = filters.get("status", "active")
    try:
        q = q.where(Lead.status == LeadStatus(seg_status))
    except ValueError:
        q = q.where(Lead.status == LeadStatus.active)

    # Filtro por tags (qualquer tag da lista)
    if tags := filters.get("tags"):
        if isinstance(tags, list) and tags:
            q = q.where(Lead.tags.op("?|")(tags))

    return (await db.execute(q)).scalar_one()


@router.get("", response_model=list[SegmentResponse])
async def list_segments(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (await db.execute(select(Segment).order_by(Segment.name))).scalars().all()
    return list(rows)


@router.get("/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    seg = await db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento não encontrado")
    return seg


@router.post("", response_model=SegmentResponse, status_code=status.HTTP_201_CREATED)
async def create_segment(
    body: SegmentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    lead_count = await _count_leads_for_filters(db, body.filters)

    seg = Segment(
        name=body.name,
        filters=body.filters,
        lead_count=lead_count,
    )
    db.add(seg)
    await db.commit()
    await db.refresh(seg)
    return seg


@router.put("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: uuid.UUID,
    body: SegmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    seg = await db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento não encontrado")

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(seg, field, value)

    # Recalcula lead_count se os filtros mudaram
    if "filters" in data:
        seg.lead_count = await _count_leads_for_filters(db, seg.filters)

    seg.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(seg)
    return seg


@router.post("/{segment_id}/refresh", response_model=SegmentResponse)
async def refresh_segment_count(
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """Recalcula o lead_count do segmento com base nos filtros atuais."""
    seg = await db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento não encontrado")

    seg.lead_count = await _count_leads_for_filters(db, seg.filters)
    seg.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(seg)
    return seg


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    seg = await db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento não encontrado")
    await db.delete(seg)
    await db.commit()
