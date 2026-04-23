"""
Webhook receiver da Evolution API.

A Evolution API envia eventos POST para esta URL quando o status de
uma mensagem muda (enviada, entregue, lida, falhou).

Payload de exemplo:
{
  "event": "messages.update",
  "instance": "wp-principal",
  "data": {
    "key": { "remoteJid": "5511999999999@s.whatsapp.net", "id": "ABCDEF123" },
    "update": { "status": "DELIVERY_ACK" }   // SENT | DELIVERY_ACK | READ | PLAYED | ERROR
  }
}

Mapeamento de status:
  SENT        → sent
  DELIVERY_ACK → delivered
  READ / PLAYED → read
  ERROR       → failed
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message, MessageStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_STATUS_MAP = {
    "SENT": MessageStatus.sent,
    "DELIVERY_ACK": MessageStatus.delivered,
    "READ": MessageStatus.read,
    "PLAYED": MessageStatus.read,
    "ERROR": MessageStatus.failed,
}

# Ordem de progressão — nunca regride
_STATUS_ORDER = [
    MessageStatus.queued,
    MessageStatus.sending,
    MessageStatus.sent,
    MessageStatus.delivered,
    MessageStatus.read,
]


def _is_progression(current: MessageStatus, new: MessageStatus) -> bool:
    """Retorna True se new é um avanço em relação a current."""
    if new == MessageStatus.failed:
        return current not in (MessageStatus.delivered, MessageStatus.read)
    try:
        return _STATUS_ORDER.index(new) > _STATUS_ORDER.index(current)
    except ValueError:
        return False


@router.post("/evolution", status_code=http_status.HTTP_200_OK)
async def evolution_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Recebe eventos da Evolution API e atualiza status das mensagens."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "reason": "invalid json"}

    event = payload.get("event", "")
    instance_name = payload.get("instance", "")
    data = payload.get("data", {})

    logger.debug(f"Webhook recebido: event={event} instance={instance_name}")

    # Só processa atualizações de mensagem
    if event not in ("messages.update", "message.update"):
        return {"ok": True, "skipped": True}

    key = data.get("key", {})
    update = data.get("update", {})
    evo_status = update.get("status", "").upper()
    remote_jid = key.get("remoteJid", "")

    if not evo_status or not remote_jid:
        return {"ok": True, "skipped": True}

    new_status = _STATUS_MAP.get(evo_status)
    if new_status is None:
        return {"ok": True, "skipped": True, "unknown_status": evo_status}

    # Extrai telefone do JID (ex: "5511999999999@s.whatsapp.net" → "+5511999999999")
    phone_raw = remote_jid.split("@")[0]
    phone = f"+{phone_raw}" if not phone_raw.startswith("+") else phone_raw

    # Busca por lead com esse telefone
    from app.models.lead import Lead
    lead_row = (await db.execute(
        select(Lead).where(Lead.phone == phone)
    )).scalar_one_or_none()

    if not lead_row:
        return {"ok": True, "skipped": True, "reason": "lead not found"}

    # Pega a mensagem mais recente do lead que ainda pode ser atualizada.
    # Filtra por statuses que aceitam progressão — evita atualizar mensagens
    # já concluídas de campanhas anteriores.
    updatable_statuses = (
        MessageStatus.sending,
        MessageStatus.sent,
        MessageStatus.delivered,
    )
    msg = (await db.execute(
        select(Message)
        .where(
            Message.lead_id == lead_row.id,
            Message.status.in_(updatable_statuses),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not msg:
        return {"ok": True, "skipped": True, "reason": "message not found"}

    if not _is_progression(msg.status, new_status):
        return {"ok": True, "skipped": True, "reason": "status would not progress"}

    old_status = msg.status
    msg.status = new_status
    now = datetime.now(timezone.utc)

    if new_status == MessageStatus.delivered:
        msg.delivered_at = now
    elif new_status == MessageStatus.read:
        msg.read_at = now

    # Atualiza contadores da campanha
    if msg.campaign_id:
        camp = await db.get(Campaign, msg.campaign_id)
        if camp:
            if new_status == MessageStatus.delivered and old_status != MessageStatus.delivered:
                camp.delivered_count += 1
                camp.updated_at = now
            elif new_status == MessageStatus.read and old_status != MessageStatus.read:
                camp.read_count += 1
                camp.updated_at = now

    await db.commit()
    logger.info(f"Mensagem {msg.id} atualizada: {old_status} → {new_status} (lead={phone})")

    return {"ok": True, "message_id": str(msg.id), "status": new_status}
