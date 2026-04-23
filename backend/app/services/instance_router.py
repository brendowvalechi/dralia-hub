"""
Instance Router — seleção inteligente de instâncias para disparo.

Estratégia: round-robin ponderado por health_score com afinidade de DDD.
- Instâncias com maior health_score têm mais chance de ser escolhidas.
- Se o número do lead tiver DDD correspondente ao número da instância, prioriza.
- Respeita daily_limit e status connected.
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance import Instance, InstanceStatus


async def pick_instance(
    db: AsyncSession,
    lead_phone: str | None = None,
    allowed_names: list[str] | None = None,
) -> Instance | None:
    """
    Escolhe a melhor instância disponível.

    - Filtra: status=connected, daily_sent < daily_limit
    - Se allowed_names informado, restringe a esse subconjunto de instâncias
    - Ordena: health_score desc
    - Aplica seleção ponderada (health_score como peso)
    - Bônus de afinidade DDD se lead_phone informado
    """
    q = (
        select(Instance)
        .where(
            Instance.status == InstanceStatus.connected,
            Instance.daily_sent < Instance.daily_limit,
        )
    )
    if allowed_names:
        q = q.where(Instance.evolution_instance_name.in_(allowed_names))

    result = await db.execute(q.order_by(Instance.health_score.desc()).limit(10))
    candidates = result.scalars().all()

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Pesos = health_score (mínimo 1 para não excluir score=0)
    weights = [max(1, c.health_score) for c in candidates]

    # Bônus DDD: se o lead tem o mesmo DDD que a instância
    if lead_phone:
        lead_ddd = _extract_ddd(lead_phone)
        for i, inst in enumerate(candidates):
            if inst.phone_number:
                inst_ddd = _extract_ddd(inst.phone_number)
                if lead_ddd and inst_ddd and lead_ddd == inst_ddd:
                    weights[i] = int(weights[i] * 1.5)

    return random.choices(candidates, weights=weights, k=1)[0]


def _extract_ddd(phone: str) -> str | None:
    """Extrai o DDD de um número E.164 brasileiro. Ex: +5511999999999 → '11'"""
    digits = "".join(c for c in phone if c.isdigit())
    # Brasil: +55 + DDD(2) + número
    if digits.startswith("55") and len(digits) >= 4:
        return digits[2:4]
    return None
