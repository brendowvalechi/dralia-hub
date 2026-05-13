"""
Instance Router — seleção inteligente de instâncias para disparo.

Estratégia: round-robin ponderado por health_score com afinidade de DDD.
- Instâncias com maior health_score têm mais chance de ser escolhidas.
- Se o número do lead tiver DDD correspondente ao número da instância, prioriza.
- Respeita daily_limit (com redutor por saúde) e status connected.
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance import Instance, InstanceStatus
from app.services import antiban_engine


def _effective_limit(inst: Instance) -> int:
    """Limite diário efetivo com redutor por saúde.

    - saúde ≥ 85: 100% do daily_limit
    - saúde 75–84: 70% do daily_limit
    - saúde < 75:  50% do daily_limit (raramente atingido pois MIN_HEALTH_SCORE=75)
    """
    h = inst.health_score
    if h >= 85:
        factor = 1.0
    elif h >= 75:
        factor = 0.7
    else:
        factor = 0.5
    return max(1, int(inst.daily_limit * factor))


async def pick_instance(
    db: AsyncSession,
    lead_phone: str | None = None,
    allowed_names: list[str] | None = None,
    use_windows: bool = False,
) -> Instance | None:
    """
    Escolhe a melhor instância disponível.

    - Filtra: status=connected, daily_sent < _effective_limit(inst)
    - Bloqueia instâncias com saúde abaixo de antiban_engine.MIN_HEALTH_SCORE
    - Se allowed_names informado, restringe a esse subconjunto de instâncias
    - Quando use_windows=True, filtra também por quota da janela atual
    - Ordena: health_score desc
    - Aplica seleção ponderada (health_score como peso)
    - Bônus de afinidade DDD se lead_phone informado
    """
    q = (
        select(Instance)
        .where(
            Instance.status == InstanceStatus.connected,
            Instance.health_score >= antiban_engine.MIN_HEALTH_SCORE,
        )
    )
    if allowed_names:
        q = q.where(Instance.evolution_instance_name.in_(allowed_names))

    result = await db.execute(q.order_by(Instance.health_score.desc()).limit(10))
    candidates = result.scalars().all()

    # Aplica limite efetivo por saúde (filtro em Python — depende de _effective_limit)
    candidates = [c for c in candidates if c.daily_sent < _effective_limit(c)]

    # Filtro de janelas: quota proporcional ao limite efetivo
    if use_windows and candidates:
        quota_pct = antiban_engine.current_window_quota_pct()
        if quota_pct is None:
            return None
        candidates = [c for c in candidates if c.daily_sent < int(_effective_limit(c) * quota_pct)]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Pesos proporcionais ao health_score
    weights = [c.health_score for c in candidates]

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
