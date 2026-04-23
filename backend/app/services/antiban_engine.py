"""
Anti-ban Engine — controla delays, horário comercial e limites diários.

Regras:
- Delay base gaussiano entre MIN_DELAY e MAX_DELAY segundos
- Jitter de ±JITTER_PCT% sobre o delay calculado
- Só envia em horário comercial BRT (UTC-3): 08:00–20:00
- Respeita daily_limit por instância
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta

# Parâmetros configuráveis
MIN_DELAY = 15       # segundos
MAX_DELAY = 90       # segundos
JITTER_PCT = 0.30    # ±30 %
BRT = timezone(timedelta(hours=-3))
BUSINESS_START = 8   # hora BRT
BUSINESS_END = 20    # hora BRT (exclusive)


def _gaussian_delay() -> float:
    """Delay gaussiano entre MIN e MAX com jitter."""
    mu = (MIN_DELAY + MAX_DELAY) / 2
    sigma = (MAX_DELAY - MIN_DELAY) / 6
    base = max(MIN_DELAY, min(MAX_DELAY, random.gauss(mu, sigma)))
    jitter = base * JITTER_PCT * random.uniform(-1, 1)
    return max(1.0, base + jitter)


def is_business_hours(dt: datetime | None = None) -> bool:
    """Retorna True se o horário atual (BRT) estiver no intervalo comercial."""
    now = (dt or datetime.now(timezone.utc)).astimezone(BRT)
    return BUSINESS_START <= now.hour < BUSINESS_END


def seconds_until_business_hours() -> float:
    """Quantos segundos faltam até abrir o horário comercial."""
    now = datetime.now(timezone.utc).astimezone(BRT)
    if is_business_hours(now):
        return 0.0
    # Calcula próximo BUSINESS_START
    if now.hour < BUSINESS_START:
        target = now.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
    else:
        # Já passou das 20h — próximo dia
        target = (now + timedelta(days=1)).replace(
            hour=BUSINESS_START, minute=0, second=0, microsecond=0
        )
    return (target - now).total_seconds()


async def wait_between_messages() -> None:
    """Aguarda o delay anti-ban entre envios."""
    delay = _gaussian_delay()
    await asyncio.sleep(delay)


async def wait_for_business_hours() -> None:
    """Se fora do horário comercial, dorme até abrir."""
    wait = seconds_until_business_hours()
    if wait > 0:
        await asyncio.sleep(wait)


def can_send(daily_sent: int, daily_limit: int) -> bool:
    """Verifica se a instância ainda pode enviar hoje."""
    return daily_sent < daily_limit
