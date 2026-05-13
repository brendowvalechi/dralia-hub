"""
Task Celery: executa o disparo de uma campanha completa.

Fluxo por lead:
  1. Aguarda horário comercial
  2. Escolhe instância disponível (round-robin por health_score)
  3. Renderiza mensagem com Spintax + variáveis do lead
  4. Simula "digitando..." (anti-ban)
  5. Envia mensagem via Evolution API
  6. Registra resultado na tabela messages
  7. Aguarda delay gaussiano (anti-ban) antes do próximo
"""
import asyncio
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app
from app.config import settings
from app.models.campaign import Campaign, CampaignStatus
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.services import antiban_engine, evolution_client, spintax_engine
from app.services.evolution_client import extract_error
from app.services.instance_router import pick_instance

from sqlalchemy import or_, select, text, update, exists
from app.services.antiban_engine import _NO_WHATSAPP_TOKENS

logger = get_task_logger(__name__)


def _make_worker_session() -> async_sessionmaker:
    """Cria engine com NullPool para uso em asyncio.run() do Celery.

    asyncpg é ligado ao event loop em que a conexão foi criada.
    asyncio.run() cria um novo event loop a cada chamada, então o pool
    compartilhado do engine principal causaria InterfaceError. NullPool
    cria uma conexão nova por session e não mantém estado entre loops.
    """
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=NullPool)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _pick_instance(db) -> Instance | None:
    """Escolhe a instância conectada com maior health_score que ainda tem limite diário."""
    result = await db.execute(
        select(Instance)
        .where(
            Instance.status == InstanceStatus.connected,
            Instance.daily_sent < Instance.daily_limit,
        )
        .order_by(Instance.health_score.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _run_campaign_async(campaign_id: str) -> None:
    cid = uuid.UUID(campaign_id)

    async with _make_worker_session()() as db:
        # Lock de sessão PostgreSQL: garante que apenas um worker execute esta campanha.
        # pg_try_advisory_lock retorna false se outro worker já adquiriu o lock.
        # O lock é liberado automaticamente quando a conexão fecha.
        lock_key = cid.int % (2**31)
        has_lock = (await db.execute(text(f"SELECT pg_try_advisory_lock({lock_key})"))).scalar()
        if not has_lock:
            logger.warning(f"Campanha {cid}: outro worker já está em execução. Abortando duplicata.")
            return

        camp = await db.get(Campaign, cid)
        if not camp or camp.status != CampaignStatus.running:
            return

        # Resolve mensagens travadas em 'sending' há mais de 10 min (worker anterior crashou
        # entre o commit de 'sending' e o de 'sent'/'failed'). Sem essa limpeza o lead ficaria
        # bloqueado para sempre, pois 'sending' está na lista de exclusão da subquery abaixo.
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale_fixed = (await db.execute(
            update(Message)
            .where(
                Message.campaign_id == cid,
                Message.status == MessageStatus.sending,
                Message.created_at < stale_cutoff,
            )
            .values(
                status=MessageStatus.failed,
                failure_reason="Timeout: worker reiniciado antes de confirmar envio",
            )
        )).rowcount
        if stale_fixed:
            logger.warning(f"Campanha {cid}: {stale_fixed} mensagens travadas em 'sending' marcadas como falha.")
        await db.commit()

        # Subquery de exclusão: leads já enviados com sucesso ou em andamento.
        already_sent_subq = (
            select(Message.lead_id)
            .where(
                Message.campaign_id == cid,
                Message.status.in_([
                    MessageStatus.sent,
                    MessageStatus.delivered,
                    MessageStatus.read,
                    MessageStatus.sending,
                ]),
            )
            .scalar_subquery()
        )

        # Subquery de exclusão permanente: leads que não têm WhatsApp.
        # Esses leads falharam com "exists:false" ou equivalente e nunca vão
        # ter sucesso — excluí-los evita retentativas infinitas a cada retomada.
        no_whatsapp_subq = (
            select(Message.lead_id)
            .where(
                Message.campaign_id == cid,
                Message.status == MessageStatus.failed,
                or_(*[
                    Message.failure_reason.ilike(f"%{token}%")
                    for token in _NO_WHATSAPP_TOKENS
                ]),
            )
            .scalar_subquery()
        )

        leads_q = (
            select(Lead)
            .where(
                Lead.status == LeadStatus.active,
                Lead.id.not_in(already_sent_subq),
                Lead.id.not_in(no_whatsapp_subq),
            )
        )
        if camp.lead_group:
            leads_q = leads_q.where(Lead.tags.contains([camp.lead_group]))
        leads_q = leads_q.order_by(Lead.created_at)

        leads = (await db.execute(leads_q)).scalars().all()
        logger.info(f"Campanha {cid}: {len(leads)} leads pendentes para envio.")

        # Fila mutável: leads transitórios são recolocados no final para retry.
        pending: deque[Lead] = deque(leads)
        # Contador de tentativas transitórias por lead (evita loop infinito).
        transient_retries: dict[uuid.UUID, int] = {}
        MAX_TRANSIENT_RETRIES = 3

        while pending:
            lead = pending.popleft()

            # Recarrega status da campanha (pode ter sido pausada/cancelada)
            await db.refresh(camp)
            if camp.status != CampaignStatus.running:
                logger.info(f"Campanha {cid} interrompida (status={camp.status})")
                return

            # Aguarda horário comercial
            await antiban_engine.wait_for_business_hours()

            if camp.use_windows:
                wait = await antiban_engine.wait_for_next_window()
                if wait > 0:
                    logger.info(f"Campanha {cid}: aguardou {wait:.0f}s até a próxima janela.")
                    await db.refresh(camp)
                    if camp.status != CampaignStatus.running:
                        return

            # Verificação definitiva por lead (cobre race conditions e retomadas).
            # Também exclui definitivamente leads sem WhatsApp para não retentar.
            already_sent = (await db.execute(
                select(Message.id)
                .where(
                    Message.campaign_id == cid,
                    Message.lead_id == lead.id,
                    Message.status.in_([
                        MessageStatus.sent,
                        MessageStatus.delivered,
                        MessageStatus.read,
                        MessageStatus.sending,
                    ]),
                )
                .limit(1)
            )).scalar_one_or_none()
            if already_sent:
                logger.warning(f"Lead {lead.id} ({lead.phone}) já processado — pulando duplicata.")
                continue

            already_no_whatsapp = (await db.execute(
                select(Message.id)
                .where(
                    Message.campaign_id == cid,
                    Message.lead_id == lead.id,
                    Message.status == MessageStatus.failed,
                    or_(*[
                        Message.failure_reason.ilike(f"%{token}%")
                        for token in _NO_WHATSAPP_TOKENS
                    ]),
                )
                .limit(1)
            )).scalar_one_or_none()
            if already_no_whatsapp:
                logger.info(f"Lead {lead.phone} sem WhatsApp confirmado — ignorando.")
                continue

            # Escolhe instância (round-robin ponderado por health_score + afinidade DDD)
            instance = await pick_instance(
                db,
                lead_phone=lead.phone,
                allowed_names=camp.allowed_instances or None,
                use_windows=camp.use_windows,
            )
            if not instance:
                if camp.use_windows and antiban_engine.current_window_quota_pct() is not None:
                    wait = await antiban_engine.wait_for_next_window()
                    if wait > 0:
                        logger.info(
                            f"Campanha {cid}: cota da janela atual atingida em todas instâncias, "
                            f"aguardando {wait:.0f}s até próximo bloco."
                        )
                        await db.refresh(camp)
                        if camp.status != CampaignStatus.running:
                            return
                        instance = await pick_instance(
                            db,
                            lead_phone=lead.phone,
                            allowed_names=camp.allowed_instances or None,
                            use_windows=camp.use_windows,
                        )
                if not instance:
                    logger.warning(
                        f"Campanha {cid}: sem instâncias disponíveis "
                        "(limite diário atingido, saúde baixa ou em quarentena). "
                        "Pausando campanha."
                    )
                    camp.status = CampaignStatus.paused
                    camp.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    return

            # Renderiza mensagem
            variables = {
                "nome": lead.name or "",
                "phone": lead.phone,
                **(lead.custom_fields or {}),
            }
            content = spintax_engine.render(camp.message_template, variables)

            # Registra mensagem como "sending"
            msg = Message(
                campaign_id=cid,
                lead_id=lead.id,
                instance_id=instance.id,
                content=content,
                media_url=camp.media_url,
                status=MessageStatus.sending,
            )
            db.add(msg)
            instance.daily_sent += 1
            await db.commit()
            await db.refresh(msg)

            try:
                is_audio_ptt = camp.media_url and camp.media_type and camp.media_type.value == "audio"

                if is_audio_ptt:
                    recording_ms = int(antiban_engine._gaussian_delay() * 200)
                    await evolution_client.send_recording(
                        instance.evolution_instance_name, lead.phone, recording_ms
                    )
                    await asyncio.sleep(recording_ms / 1000)
                else:
                    typing_ms = int(antiban_engine._gaussian_delay() * 200)
                    await evolution_client.send_typing(
                        instance.evolution_instance_name, lead.phone, typing_ms
                    )
                    await asyncio.sleep(typing_ms / 1000)

                if content and is_audio_ptt:
                    await evolution_client.send_text(
                        instance.evolution_instance_name, lead.phone, content
                    )
                    await asyncio.sleep(1.5)

                if is_audio_ptt:
                    await evolution_client.send_audio_ptt(
                        instance.evolution_instance_name,
                        lead.phone,
                        camp.media_url,
                    )
                elif camp.media_url and camp.media_type:
                    await evolution_client.send_media(
                        instance.evolution_instance_name,
                        lead.phone,
                        camp.media_url,
                        camp.media_type.value,
                        content,
                    )
                else:
                    await evolution_client.send_text(
                        instance.evolution_instance_name, lead.phone, content
                    )

                msg.status = MessageStatus.sent
                msg.sent_at = datetime.now(timezone.utc)
                camp.sent_count += 1
                instance.consecutive_failures = 0

            except Exception as exc:
                err_str = extract_error(exc)
                severity = antiban_engine.classify_error(err_str)
                logger.error(f"Erro ao enviar para {lead.phone} [{type(exc).__name__}] severity={severity}: {err_str}")

                if severity == "transient":
                    # Remove o registro de envio e devolve o slot ao limite diário.
                    # O lead é reinserido na fila para ser retentado com outra instância.
                    await db.delete(msg)
                    instance.daily_sent = max(0, instance.daily_sent - 1)
                    instance.updated_at = datetime.now(timezone.utc)
                    camp.updated_at = datetime.now(timezone.utc)
                    await db.commit()

                    retry_n = transient_retries.get(lead.id, 0) + 1
                    transient_retries[lead.id] = retry_n
                    if retry_n <= MAX_TRANSIENT_RETRIES:
                        logger.warning(
                            f"Transitório para {lead.phone} (tentativa {retry_n}/{MAX_TRANSIENT_RETRIES}), "
                            f"reagendando: {err_str}"
                        )
                        pending.append(lead)
                    else:
                        logger.error(
                            f"Lead {lead.phone}: esgotadas {MAX_TRANSIENT_RETRIES} tentativas "
                            f"transitórias — registrando falha definitiva."
                        )
                        fail_msg = Message(
                            campaign_id=cid,
                            lead_id=lead.id,
                            instance_id=instance.id,
                            content=content,
                            media_url=camp.media_url,
                            status=MessageStatus.failed,
                            failure_reason=f"[{MAX_TRANSIENT_RETRIES}x tentativas] {err_str}",
                        )
                        db.add(fail_msg)
                        camp.failed_count += 1
                        camp.updated_at = datetime.now(timezone.utc)
                        instance.updated_at = datetime.now(timezone.utc)
                        await db.commit()

                    # Pula o commit/delay do fim do loop (já commitado acima)
                    await antiban_engine.wait_between_messages()
                    continue

                # Falhas não-transitórias: marca como falida e penaliza instância
                msg.status = MessageStatus.failed
                msg.failure_reason = err_str
                camp.failed_count += 1

                if severity == "no_whatsapp":
                    pass  # Número sem WhatsApp — instância não tem culpa
                elif severity == "severe":
                    instance.health_score = max(0, instance.health_score - 15)
                    instance.consecutive_failures += 1
                    instance.status = InstanceStatus.quarantine
                    logger.error(
                        f"Instância {instance.evolution_instance_name} em QUARENTENA "
                        f"após erro grave: {err_str[:120]}"
                    )
                else:  # mild
                    instance.health_score = max(0, instance.health_score - 2)
                    instance.consecutive_failures += 1
                    if instance.consecutive_failures >= antiban_engine.MAX_CONSECUTIVE_FAILURES:
                        instance.status = InstanceStatus.quarantine
                        logger.error(
                            f"Instância {instance.evolution_instance_name} em QUARENTENA: "
                            f"{instance.consecutive_failures} falhas consecutivas."
                        )

            camp.updated_at = datetime.now(timezone.utc)
            instance.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Delay anti-ban entre mensagens
            await antiban_engine.wait_between_messages()

        # Campanha concluída
        await db.refresh(camp)
        if camp.status == CampaignStatus.running:
            camp.status = CampaignStatus.completed
            camp.completed_at = datetime.now(timezone.utc)
            camp.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(f"Campanha {cid} concluída. Enviadas: {camp.sent_count}, Falhas: {camp.failed_count}")


@celery_app.task(bind=True, name="campaign_worker.run_campaign", max_retries=0)
def run_campaign(self, campaign_id: str) -> None:
    """Entry-point Celery — executa a corrotina async no event loop."""
    logger.info(f"Iniciando campanha {campaign_id}")
    asyncio.run(_run_campaign_async(campaign_id))
