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

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.models.segment import Segment
from app.services import warmup_manager

logger = get_task_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# reset_daily_sent — meia-noite BRT
# ─────────────────────────────────────────────────────────────────────────────
async def _reset_daily_sent_async() -> int:
    async with SessionLocal() as db:
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
    async with SessionLocal() as db:
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
    async with SessionLocal() as db:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        result = await db.execute(select(Instance))
        instances = result.scalars().all()

        for inst in instances:
            # Conta mensagens do dia por status
            def count_status(s: MessageStatus):
                return select(func.count(Message.id)).where(
                    Message.instance_id == inst.id,
                    Message.status == s,
                    Message.sent_at >= today_start,
                )

            sent = (await db.execute(count_status(MessageStatus.sent))).scalar_one()
            delivered = (await db.execute(count_status(MessageStatus.delivered))).scalar_one()
            read = (await db.execute(count_status(MessageStatus.read))).scalar_one()
            failed = (await db.execute(count_status(MessageStatus.failed))).scalar_one()

            total = sent + delivered + read + failed
            if total == 0:
                continue

            delta = warmup_manager.calculate_health_delta(
                sent=total, delivered=delivered + read, failed=failed, read=read
            )
            inst.health_score = warmup_manager.clamp_health(inst.health_score + delta)
            logger.info(
                f"Instância {inst.display_name}: health_score={inst.health_score} (delta={delta:+})"
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

    async with SessionLocal() as db:
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
