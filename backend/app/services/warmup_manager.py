"""
Warm-up Manager: protocolo de 30 dias para novas instâncias WhatsApp.

Cronograma de volume diário (baseado em boas práticas anti-ban):
  Dias 1-3:   20 msgs/dia
  Dias 4-7:   50 msgs/dia
  Dias 8-14: 100 msgs/dia
  Dias 15-21: 200 msgs/dia
  Dias 22-30: 300 msgs/dia
  Dia 30+:    limite configurado (produção)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

WARMUP_SCHEDULE = [
    (3, 20),
    (7, 50),
    (14, 100),
    (21, 200),
    (30, 300),
]


def get_warmup_limit(warmup_day: int) -> int:
    """Retorna o limite diário de mensagens para o dia de warm-up especificado."""
    for max_day, limit in WARMUP_SCHEDULE:
        if warmup_day <= max_day:
            return limit
    return 300  # Produção após 30 dias


def is_warmed_up(warmup_day: int | None) -> bool:
    """Retorna True se a instância completou o protocolo de warm-up."""
    return warmup_day is None or warmup_day > 30


def advance_warmup_day(warmup_day: int | None) -> int | None:
    """Avança o dia de warm-up. Retorna None quando o warm-up é concluído."""
    if warmup_day is None:
        return None
    next_day = warmup_day + 1
    if next_day > 30:
        return None  # Warm-up completo
    return next_day


def calculate_health_delta(
    sent: int,
    delivered: int,
    failed: int,
    read: int,
) -> int:
    """
    Calcula o delta de health_score baseado nos resultados do dia.

    Regras:
    - Taxa de entrega < 60%: -10
    - Taxa de entrega 60-80%: 0
    - Taxa de entrega > 80%: +2
    - Taxa de leitura > 20%: +3 bônus
    - Falhas > 10 em um dia: -5
    """
    if sent == 0:
        return 0

    delivery_rate = delivered / sent
    delta = 0

    if delivery_rate < 0.60:
        delta -= 10
    elif delivery_rate > 0.80:
        delta += 2

    if sent > 0 and read / sent > 0.20:
        delta += 3

    if failed > 10:
        delta -= 5

    return delta


def clamp_health(score: int) -> int:
    return max(0, min(100, score))
