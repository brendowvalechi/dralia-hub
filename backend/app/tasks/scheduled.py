"""
Tarefas agendadas via Celery Beat.

- reset_daily_sent: zera daily_sent de todas as instâncias todo dia à meia-noite BRT
- advance_warmup: avança o dia de warm-up e ajusta daily_limit de instâncias em warm-up
- refresh_segment_counts: recalcula lead_count de todos os segmentos
- update_health_scores: recalcula health_score com base nos envios do dia
"""
import asyncio
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import func, select, update

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app
from app.config import settings
from app.models.campaign import Campaign, CampaignStatus
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.models.segment import Segment
from app.services import warmup_manager

logger = get_task_logger(__name__)


def _worker_session() -> async_sessionmaker:
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=NullPool)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────────────────────
# reset_daily_sent — meia-noite BRT
# ─────────────────────────────────────────────────────────────────────────────
async def _reset_daily_sent_async() -> int:
    async with _worker_session()() as db:
        result = await db.execute(update(Instance).values(daily_sent=0))
        await db.commit()
        return result.rowcount


@celery_app.task(name="scheduled.reset_daily_sent")
def reset_daily_sent() -> None:
    count = asyncio.run(_reset_daily_sent_async())
    logger.info(f"daily_sent zerado em {count} instâncias.")


# ─────────────────────────────────────────────────────────────────────────────
# advance_warmup — avança o dia de warm-up e ajusta daily_limit
# ─────────────────────────────────────────────────────────────────────────────
async def _advance_warmup_async() -> None:
    async with _worker_session()() as db:
        result = await db.execute(
            select(Instance).where(
                Instance.warmup_day.isnot(None),
                Instance.status == InstanceStatus.connected,
            )
        )
        instances = result.scalars().all()

        for inst in instances:
            next_day = warmup_manager.advance_warmup_day(inst.warmup_day)
            new_limit = warmup_manager.get_warmup_limit(next_day or 31)
            inst.warmup_day = next_day
            inst.daily_limit = new_limit
            logger.info(
                f"Instância {inst.display_name}: warm-up dia {next_day}, "
                f"novo limite={new_limit}"
            )

        await db.commit()


@celery_app.task(name="scheduled.advance_warmup")
def advance_warmup() -> None:
    asyncio.run(_advance_warmup_async())


# ─────────────────────────────────────────────────────────────────────────────
# update_health_scores — recalcula health_score com base nos envios do dia
# ─────────────────────────────────────────────────────────────────────────────
async def _update_health_scores_async() -> None:
    from app.services.antiban_engine import BRT

    async with _worker_session()() as db:
        # today_start em BRT: garante que mensagens enviadas hoje (horário brasileiro)
        # sejam contadas mesmo quando a task roda às 23:55 BRT = 02:55 UTC+1.
        now_brt = datetime.now(BRT)
        today_start = now_brt.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        result = await db.execute(select(Instance))
        instances = result.scalars().all()

        for inst in instances:
            sent = (await db.execute(
                select(func.count(Message.id)).where(
                    Message.instance_id == inst.id,
                    Message.status == MessageStatus.sent,
                    Message.sent_at >= today_start,
                )
            )).scalar_one()
            delivered = (await db.execute(
                select(func.count(Message.id)).where(
                    Message.instance_id == inst.id,
                    Message.status == MessageStatus.delivered,
                    Message.sent_at >= today_start,
                )
            )).scalar_one()
            read = (await db.execute(
                select(func.count(Message.id)).where(
                    Message.instance_id == inst.id,
                    Message.status == MessageStatus.read,
                    Message.sent_at >= today_start,
                )
            )).scalar_one()
            # Mensagens com falha não têm sent_at — usa created_at
            failed = (await db.execute(
                select(func.count(Message.id)).where(
                    Message.instance_id == inst.id,
                    Message.status == MessageStatus.failed,
                    Message.created_at >= today_start,
                )
            )).scalar_one()

            total = sent + delivered + read + failed

            if total == 0:
                # Sem atividade hoje: recuperação passiva para instâncias conectadas.
                # +2 por dia de descanso, máximo 90 (nunca chega a 100 só descansando).
                if inst.status == InstanceStatus.connected and inst.health_score < 90:
                    inst.health_score = min(inst.health_score + 2, 90)
                    inst.updated_at = datetime.now(timezone.utc)
                    logger.info(
                        f"Instância {inst.display_name}: descanso → health_score={inst.health_score} (+2)"
                    )
                continue

            delta = warmup_manager.calculate_health_delta(
                sent=total, delivered=delivered + read, failed=failed, read=read
            )
            inst.health_score = warmup_manager.clamp_health(inst.health_score + delta)
            inst.updated_at = datetime.now(timezone.utc)
            logger.info(
                f"Instância {inst.display_name}: health_score={inst.health_score} (delta={delta:+}, "
                f"enviadas={sent}, entregues={delivered+read}, falhas={failed})"
            )

        await db.commit()


@celery_app.task(name="scheduled.update_health_scores")
def update_health_scores() -> None:
    asyncio.run(_update_health_scores_async())


# ─────────────────────────────────────────────────────────────────────────────
# refresh_segment_counts — recalcula lead_count de todos os segmentos
# ─────────────────────────────────────────────────────────────────────────────
async def _refresh_segment_counts_async() -> None:
    from app.models.lead import LeadStatus

    async with _worker_session()() as db:
        segments = (await db.execute(select(Segment))).scalars().all()

        for seg in segments:
            filters = seg.filters or {}
            q = select(func.count(Lead.id))

            seg_status = filters.get("status", "active")
            try:
                q = q.where(Lead.status == LeadStatus(seg_status))
            except ValueError:
                q = q.where(Lead.status == LeadStatus.active)

            if tags := filters.get("tags"):
                if isinstance(tags, list) and tags:
                    q = q.where(Lead.tags.op("?|")(tags))

            seg.lead_count = (await db.execute(q)).scalar_one()

        await db.commit()
        logger.info(f"lead_count atualizado em {len(segments)} segmentos.")


@celery_app.task(name="scheduled.refresh_segment_counts")
def refresh_segment_counts() -> None:
    asyncio.run(_refresh_segment_counts_async())


# ─────────────────────────────────────────────────────────────────────────────
# launch_scheduled_campaigns — verifica campanhas agendadas e as lança no horário
# ─────────────────────────────────────────────────────────────────────────────
async def _launch_scheduled_campaigns_async() -> None:
    now = datetime.now(timezone.utc)

    async with _worker_session()() as db:
        result = await db.execute(
            select(Campaign).where(
                Campaign.status == CampaignStatus.scheduled,
                Campaign.scheduled_at <= now,
            )
        )
        due = result.scalars().all()

        for camp in due:
            camp.status = CampaignStatus.running
            camp.started_at = now
            camp.updated_at = now
            logger.info(f"Lançando campanha agendada: {camp.name} ({camp.id})")

        await db.commit()

    # Envia tasks ao worker fora da sessão (após commit)
    for camp in due:
        from app.tasks.campaign_worker import run_campaign
        run_campaign.delay(str(camp.id))


@celery_app.task(name="scheduled.launch_scheduled_campaigns")
def launch_scheduled_campaigns() -> None:
    asyncio.run(_launch_scheduled_campaigns_async())
