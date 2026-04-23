"""
Dashboard — métricas agregadas da plataforma.

Endpoints:
  GET /dashboard/overview   — totais gerais (leads, campanhas, instâncias, mensagens)
  GET /dashboard/campaigns  — desempenho das últimas N campanhas
  GET /dashboard/instances  — saúde das instâncias WhatsApp
  GET /dashboard/messages   — volume de mensagens por dia (últimos N dias)
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# OVERVIEW — números gerais
# ---------------------------------------------------------------------------
@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Leads
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    active_leads = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.active)
    )).scalar_one()
    opted_out = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.opted_out)
    )).scalar_one()

    # Campanhas
    total_campaigns = (await db.execute(select(func.count(Campaign.id)))).scalar_one()
    running_campaigns = (await db.execute(
        select(func.count(Campaign.id)).where(Campaign.status == CampaignStatus.running)
    )).scalar_one()
    completed_campaigns = (await db.execute(
        select(func.count(Campaign.id)).where(Campaign.status == CampaignStatus.completed)
    )).scalar_one()

    # Instâncias
    total_instances = (await db.execute(select(func.count(Instance.id)))).scalar_one()
    connected_instances = (await db.execute(
        select(func.count(Instance.id)).where(Instance.status == InstanceStatus.connected)
    )).scalar_one()

    # Mensagens (total e por status)
    total_messages = (await db.execute(select(func.count(Message.id)))).scalar_one()
    sent_messages = (await db.execute(
        select(func.count(Message.id)).where(Message.status == MessageStatus.sent)
    )).scalar_one()
    delivered_messages = (await db.execute(
        select(func.count(Message.id)).where(Message.status == MessageStatus.delivered)
    )).scalar_one()
    failed_messages = (await db.execute(
        select(func.count(Message.id)).where(Message.status == MessageStatus.failed)
    )).scalar_one()

    delivery_rate = round(delivered_messages / sent_messages * 100, 1) if sent_messages > 0 else 0.0

    return {
        "leads": {
            "total": total_leads,
            "active": active_leads,
            "opted_out": opted_out,
        },
        "campaigns": {
            "total": total_campaigns,
            "running": running_campaigns,
            "completed": completed_campaigns,
        },
        "instances": {
            "total": total_instances,
            "connected": connected_instances,
        },
        "messages": {
            "total": total_messages,
            "sent": sent_messages,
            "delivered": delivered_messages,
            "failed": failed_messages,
            "delivery_rate_pct": delivery_rate,
        },
    }


# ---------------------------------------------------------------------------
# CAMPAIGNS — desempenho das últimas N campanhas concluídas
# ---------------------------------------------------------------------------
@router.get("/campaigns")
async def campaign_performance(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Campaign)
            .where(Campaign.status.in_([CampaignStatus.completed, CampaignStatus.running, CampaignStatus.failed]))
            .order_by(Campaign.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    result = []
    for c in rows:
        delivery_rate = round(c.delivered_count / c.sent_count * 100, 1) if c.sent_count > 0 else 0.0
        read_rate = round(c.read_count / c.delivered_count * 100, 1) if c.delivered_count > 0 else 0.0
        result.append({
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "total_leads": c.total_leads,
            "sent_count": c.sent_count,
            "delivered_count": c.delivered_count,
            "read_count": c.read_count,
            "failed_count": c.failed_count,
            "delivery_rate_pct": delivery_rate,
            "read_rate_pct": read_rate,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        })

    return {"campaigns": result}


# ---------------------------------------------------------------------------
# INSTANCES — saúde das instâncias
# ---------------------------------------------------------------------------
@router.get("/instances")
async def instance_health(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Instance).order_by(Instance.health_score.desc())
        )
    ).scalars().all()

    result = []
    for inst in rows:
        result.append({
            "id": str(inst.id),
            "display_name": inst.display_name,
            "evolution_instance_name": inst.evolution_instance_name,
            "phone_number": inst.phone_number,
            "status": inst.status,
            "health_score": inst.health_score,
            "daily_sent": inst.daily_sent,
            "daily_limit": inst.daily_limit,
            "daily_usage_pct": round(inst.daily_sent / inst.daily_limit * 100, 1) if inst.daily_limit > 0 else 0.0,
            "warmup_day": inst.warmup_day,
            "ban_count": inst.ban_count,
            "last_connected_at": inst.last_connected_at.isoformat() if inst.last_connected_at else None,
        })

    return {"instances": result}


# ---------------------------------------------------------------------------
# MESSAGES — volume diário (últimos N dias)
# ---------------------------------------------------------------------------
@router.get("/messages")
async def message_volume(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Agrupa por data — usa CAST(sent_at AS DATE) para evitar problema com date_trunc como parâmetro
    from sqlalchemy import cast, case, Date, text
    day_expr = cast(Message.sent_at, Date).label("day")
    rows = (
        await db.execute(
            select(
                day_expr,
                func.count(Message.id).label("total"),
                func.count(case((Message.status == MessageStatus.sent, 1))).label("sent"),
                func.count(case((Message.status == MessageStatus.delivered, 1))).label("delivered"),
                func.count(case((Message.status == MessageStatus.failed, 1))).label("failed"),
            )
            .where(Message.sent_at >= since)
            .group_by(cast(Message.sent_at, Date))
            .order_by(cast(Message.sent_at, Date))
        )
    ).all()

    return {
        "days": days,
        "since": since.date().isoformat(),
        "series": [
            {
                "date": str(r.day.date()) if r.day else None,
                "total": r.total,
                "sent": r.sent or 0,
                "delivered": r.delivered or 0,
                "failed": r.failed or 0,
            }
            for r in rows
        ],
    }
