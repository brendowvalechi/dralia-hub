"""
Prometheus metrics endpoint — expõe métricas do sistema para Grafana.
Rota: GET /metrics (texto plano, formato Prometheus)
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.instance import Instance, InstanceStatus
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageStatus

router = APIRouter(tags=["metrics"])


def _gauge(name: str, value: float | int, labels: dict | None = None, help_text: str = "") -> str:
    label_str = ""
    if labels:
        parts = [f'{k}="{v}"' for k, v in labels.items()]
        label_str = "{" + ",".join(parts) + "}"
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name}{label_str} {value}")
    return "\n".join(lines)


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(db: AsyncSession = Depends(get_db)):
    lines = []

    # ── Leads ────────────────────────────────────────────────────────────────
    for ls in LeadStatus:
        cnt = (await db.execute(select(func.count(Lead.id)).where(Lead.status == ls))).scalar_one()
        lines.append(_gauge("p3f_leads_total", cnt, {"status": ls.value}, "Total de leads por status"))

    # ── Instâncias ───────────────────────────────────────────────────────────
    for inst_status in InstanceStatus:
        cnt = (await db.execute(select(func.count(Instance.id)).where(Instance.status == inst_status))).scalar_one()
        lines.append(_gauge("p3f_instances_total", cnt, {"status": inst_status.value}, "Instâncias por status"))

    # Health score médio
    avg_health = (await db.execute(select(func.avg(Instance.health_score)))).scalar_one() or 0
    lines.append(_gauge("p3f_instance_health_avg", round(float(avg_health), 2), help_text="Health score médio das instâncias"))

    # ── Campanhas ────────────────────────────────────────────────────────────
    for camp_status in CampaignStatus:
        cnt = (await db.execute(select(func.count(Campaign.id)).where(Campaign.status == camp_status))).scalar_one()
        lines.append(_gauge("p3f_campaigns_total", cnt, {"status": camp_status.value}, "Campanhas por status"))

    # ── Mensagens ────────────────────────────────────────────────────────────
    for msg_status in MessageStatus:
        cnt = (await db.execute(select(func.count(Message.id)).where(Message.status == msg_status))).scalar_one()
        lines.append(_gauge("p3f_messages_total", cnt, {"status": msg_status.value}, "Mensagens por status"))

    # Taxa de entrega global
    total_sent = (await db.execute(select(func.count(Message.id)).where(Message.status != MessageStatus.sending))).scalar_one()
    total_delivered = (await db.execute(select(func.count(Message.id)).where(Message.status == MessageStatus.delivered))).scalar_one()
    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    lines.append(_gauge("p3f_delivery_rate_pct", round(delivery_rate, 2), help_text="Taxa de entrega global (%)"))

    body = "\n\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
