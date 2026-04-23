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
from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.campaign import Campaign, CampaignStatus
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus
from app.services import antiban_engine, evolution_client, spintax_engine
from app.services.instance_router import pick_instance

from sqlalchemy import select, update, exists

logger = get_task_logger(__name__)


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

    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        if not camp or camp.status != CampaignStatus.running:
            return

        # Carrega apenas leads que AINDA NÃO receberam mensagem nesta campanha
        # (exclui leads com mensagem em status sent/delivered/read/sending)
        # Isso garante que pausar+retomar não reenvie mensagens já processadas.
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

            # Escolhe instância (round-robin ponderado por health_score + afinidade DDD)
            instance = await pick_instance(
                db,
                lead_phone=lead.phone,
                allowed_names=camp.allowed_instances or None,
            )
            if not instance:
                # Sem instância disponível = limite diário atingido.
                # Pausa a campanha em vez de marcar como falha.
                # O operador pode retomar no dia seguinte (limite é resetado às meia-noite).
                logger.warning(
                    f"Campanha {cid}: sem instâncias disponíveis (limite diário atingido?). "
                    "Pausando campanha — retome amanhã."
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

            except Exception as exc:
                logger.error(f"Erro ao enviar para {lead.phone}: {exc}")
                msg.status = MessageStatus.failed
                msg.failure_reason = str(exc)[:500]
                camp.failed_count += 1
                # Penaliza health_score
                instance.health_score = max(0, instance.health_score - 2)

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
