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
from app.services.instance_router import pick_instance

from sqlalchemy import select, text, update, exists

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

        # Subquery de exclusão inicial: leads que já têm mensagem processada com sucesso
        # ou ainda em andamento. Funciona como pré-filtro rápido; a verificação definitiva
        # ocorre por lead dentro do loop (ver adiante).
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

        leads_q = (
            select(Lead)
            .where(
                Lead.status == LeadStatus.active,
                Lead.id.not_in(already_sent_subq),
            )
        )
        if camp.lead_group:
            leads_q = leads_q.where(Lead.tags.contains([camp.lead_group]))
        leads_q = leads_q.order_by(Lead.created_at)

        leads = (await db.execute(leads_q)).scalars().all()
        logger.info(f"Campanha {cid}: {len(leads)} leads pendentes para envio.")

        for lead in leads:
            # Recarrega status da campanha (pode ter sido pausada/cancelada)
            await db.refresh(camp)
            if camp.status != CampaignStatus.running:
                logger.info(f"Campanha {cid} interrompida (status={camp.status})")
                return

            # Aguarda horário comercial
            await antiban_engine.wait_for_business_hours()

            # Janelas: se a campanha estiver configurada para distribuir
            # envios pelo dia (manhã/tarde/noite), espera o próximo bloco
            # ativo quando estamos numa pausa entre janelas.
            if camp.use_windows:
                wait = await antiban_engine.wait_for_next_window()
                if wait > 0:
                    logger.info(f"Campanha {cid}: aguardou {wait:.0f}s até a próxima janela.")
                    # Após dormir, recarrega status (pode ter sido pausada)
                    await db.refresh(camp)
                    if camp.status != CampaignStatus.running:
                        return

            # Verificação definitiva por lead: consulta o banco no momento do processamento
            # para cobrir race conditions entre workers e retomadas de campanha.
            # A subquery inicial é um pré-filtro; este SELECT é a garantia real.
            already = (await db.execute(
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
            if already:
                logger.warning(f"Lead {lead.id} ({lead.phone}) já processado — pulando duplicata.")
                continue

            # Escolhe instância (round-robin ponderado por health_score + afinidade DDD)
            instance = await pick_instance(
                db,
                lead_phone=lead.phone,
                allowed_names=camp.allowed_instances or None,
                use_windows=camp.use_windows,
            )
            if not instance:
                # Quando use_windows=True e estamos dentro de uma janela mas
                # todas instâncias bateram a quota do bloco, é melhor esperar
                # a próxima janela do que pausar a campanha.
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
                        # Volta ao topo do loop com a nova janela
                        # Reusa pick_instance — usa um pequeno truque de continue
                        # via try-except seria mais limpo, mas continue dentro
                        # do for atual já basta:
                        # (lead atual ainda não foi consumido)
                        # Nota: o `for lead in leads` itera leads pré-carregados;
                        # decrementar e re-pegar não é trivial. Em vez disso,
                        # usamos pick_instance de novo agora.
                        instance = await pick_instance(
                            db,
                            lead_phone=lead.phone,
                            allowed_names=camp.allowed_instances or None,
                            use_windows=camp.use_windows,
                        )
                if not instance:
                    # Sem instância disponível = limite diário atingido OU
                    # todas com saúde abaixo do mínimo OU em quarentena.
                    # Pausa a campanha — operador retoma quando resolver.
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
                    # Simula "gravando áudio…" (anti-ban para PTT)
                    recording_ms = int(antiban_engine._gaussian_delay() * 200)
                    await evolution_client.send_recording(
                        instance.evolution_instance_name, lead.phone, recording_ms
                    )
                    await asyncio.sleep(recording_ms / 1000)
                else:
                    # Simula digitando (anti-ban para texto/mídia)
                    typing_ms = int(antiban_engine._gaussian_delay() * 200)
                    await evolution_client.send_typing(
                        instance.evolution_instance_name, lead.phone, typing_ms
                    )
                    await asyncio.sleep(typing_ms / 1000)

                # Envia texto de introdução se houver template + áudio
                if content and is_audio_ptt:
                    await evolution_client.send_text(
                        instance.evolution_instance_name, lead.phone, content
                    )
                    await asyncio.sleep(1.5)

                # Envia a mensagem principal
                if is_audio_ptt:
                    # Áudio como PTT (voz) — não aparece como "encaminhado"
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
                # Reseta o contador de falhas consecutivas a cada envio OK.
                # É o sinal de que a instância continua saudável.
                instance.consecutive_failures = 0

            except Exception as exc:
                err_str = str(exc)[:500]
                logger.error(f"Erro ao enviar para {lead.phone}: {err_str}")
                msg.status = MessageStatus.failed
                msg.failure_reason = err_str
                camp.failed_count += 1

                # Classifica a falha para decidir penalidade e auto-pausa.
                # 'no_whatsapp' = lead inválido; instância não tem culpa.
                # 'severe'      = ban/sessão derrubada; penalidade alta.
                # 'mild'        = erro genérico; penalidade pequena.
                severity = antiban_engine.classify_error(err_str)

                if severity == "no_whatsapp":
                    # Não penaliza saúde nem incrementa falhas consecutivas.
                    pass
                elif severity == "severe":
                    instance.health_score = max(0, instance.health_score - 15)
                    instance.consecutive_failures += 1
                    # Erro grave isolado já é suficiente para tirar a instância
                    # do circuito até intervenção humana.
                    instance.status = InstanceStatus.quarantine
                    logger.error(
                        f"Instância {instance.evolution_instance_name} colocada em "
                        f"QUARENTENA após erro grave: {err_str[:120]}"
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
