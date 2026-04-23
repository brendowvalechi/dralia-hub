import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _fire_celery(task_name: str, campaign_id: str) -> None:
    """Dispara task Celery em thread separada (não bloqueia o event loop)."""
    try:
        from app.tasks.campaign_worker import run_campaign
        run_campaign.delay(campaign_id)
    except Exception as exc:
        logger.error(f"Falha ao enfileirar {task_name} {campaign_id}: {exc}")

from app.api.deps import get_current_user, require_operator
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.models.segment import Segment
from app.models.user import User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

# Estados que permitem edição
_EDITABLE_STATUSES = {CampaignStatus.draft, CampaignStatus.scheduled}


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: CampaignStatus | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Campaign)
    if status:
        q = q.where(Campaign.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(
            q.order_by(Campaign.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return CampaignListResponse(total=total, page=page, page_size=page_size, items=list(rows))


# ---------------------------------------------------------------------------
# GET BY ID
# ---------------------------------------------------------------------------
@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    return camp


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    # Valida segment_id se informado
    if body.segment_id:
        seg = await db.get(Segment, body.segment_id)
        if not seg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento não encontrado")

    camp_status = CampaignStatus.scheduled if body.scheduled_at else CampaignStatus.draft

    camp = Campaign(
        name=body.name,
        user_id=current_user.id,
        segment_id=body.segment_id,
        message_template=body.message_template,
        media_url=body.media_url,
        media_type=body.media_type,
        scheduled_at=body.scheduled_at,
        status=camp_status,
    )
    db.add(camp)
    await db.commit()
    await db.refresh(camp)
    return camp


# ---------------------------------------------------------------------------
# UPDATE (só em draft/scheduled)
# ---------------------------------------------------------------------------
@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    if camp.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não é possível editar campanha com status '{camp.status}'",
        )

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(camp, field, value)
    camp.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(camp)
    return camp


# ---------------------------------------------------------------------------
# DELETE (só em draft)
# ---------------------------------------------------------------------------
@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    if camp.status != CampaignStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só é possível excluir campanhas em rascunho",
        )
    await db.delete(camp)
    await db.commit()


# ---------------------------------------------------------------------------
# LAUNCH — dispara a campanha (enfileira task Celery)
# ---------------------------------------------------------------------------
@router.post("/{campaign_id}/launch", response_model=CampaignResponse)
async def launch_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    if camp.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campanha já está '{camp.status}'",
        )

    # Calcula total_leads com base no segmento, grupo ou todos os leads ativos
    if camp.segment_id:
        seg = await db.get(Segment, camp.segment_id)
        total = seg.lead_count if seg else 0
    elif camp.lead_group:
        total = (
            await db.execute(
                select(func.count(Lead.id)).where(
                    Lead.status == LeadStatus.active,
                    Lead.tags.contains([camp.lead_group]),
                )
            )
        ).scalar_one()
    else:
        total = (
            await db.execute(
                select(func.count(Lead.id)).where(Lead.status == LeadStatus.active)
            )
        ).scalar_one()

    camp.status = CampaignStatus.running
    camp.started_at = datetime.now(timezone.utc)
    camp.total_leads = total
    camp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(camp)

    # Dispara Celery em background thread — não bloqueia o response mesmo com Redis offline
    asyncio.get_running_loop().run_in_executor(None, _fire_celery, "run_campaign", str(campaign_id))

    return camp


# ---------------------------------------------------------------------------
# PAUSE
# ---------------------------------------------------------------------------
@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    if camp.status != CampaignStatus.running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campanha não está em execução")

    camp.status = CampaignStatus.paused
    camp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(camp)
    return camp


# ---------------------------------------------------------------------------
# RESUME
# ---------------------------------------------------------------------------
@router.post("/{campaign_id}/resume", response_model=CampaignResponse)
async def resume_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")
    if camp.status != CampaignStatus.paused:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campanha não está pausada")

    camp.status = CampaignStatus.running
    camp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(camp)

    asyncio.get_running_loop().run_in_executor(None, _fire_celery, "run_campaign", str(campaign_id))

    return camp


# ---------------------------------------------------------------------------
# STATS — contadores de mensagens em tempo real
# ---------------------------------------------------------------------------
@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")

    counts = {}
    for msg_status in MessageStatus:
        cnt = (
            await db.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id == campaign_id,
                    Message.status == msg_status,
                )
            )
        ).scalar_one()
        counts[msg_status.value] = cnt

    return {
        "campaign_id": str(campaign_id),
        "status": camp.status,
        "total_leads": camp.total_leads,
        "messages": counts,
    }


# ---------------------------------------------------------------------------
# DELIVERY REPORT — verificação detalhada de entrega
# ---------------------------------------------------------------------------
@router.get("/{campaign_id}/delivery-report")
async def campaign_delivery_report(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    camp = await db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada")

    # Busca todas as mensagens com dados do lead
    from app.models.lead import Lead
    rows = (
        await db.execute(
            select(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .where(Message.campaign_id == campaign_id)
            .order_by(Message.sent_at.desc().nullslast())
        )
    ).all()

    summary = {s.value: 0 for s in MessageStatus}
    messages = []
    for msg, lead in rows:
        summary[msg.status.value] += 1
        messages.append({
            "message_id": str(msg.id),
            "lead_id": str(lead.id),
            "lead_name": lead.name,
            "lead_phone": lead.phone,
            "status": msg.status.value,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
            "failure_reason": msg.failure_reason,
        })

    confirmed = summary.get("delivered", 0) + summary.get("read", 0)
    total_sent = summary.get("sent", 0) + confirmed
    delivery_rate = round((confirmed / total_sent * 100), 1) if total_sent > 0 else 0

    return {
        "campaign_id": str(campaign_id),
        "campaign_name": camp.name,
        "status": camp.status,
        "total_leads": camp.total_leads,
        "summary": summary,
        "delivery_rate_pct": delivery_rate,
        "messages": messages,
    }
