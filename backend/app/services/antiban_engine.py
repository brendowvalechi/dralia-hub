"""
Anti-ban Engine — controla delays, horário comercial, janelas de envio e
thresholds de saúde.

Regras gerais:
- Delay base gaussiano entre MIN_DELAY e MAX_DELAY segundos (com jitter)
- Só envia em horário comercial BRT (UTC-3): 08:00–20:00
- Respeita daily_limit por instância
- Bloqueia envios para instâncias com health_score < MIN_HEALTH_SCORE
- Quando a campanha usa janelas, distribui o disparo em 3 blocos do dia
  (manhã/tarde/noite) com pausas de almoço e jantar
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# Parâmetros de delay (subimos de 15-90 para 30-180s para reduzir risco de ban)
# ─────────────────────────────────────────────────────────────────────────────
MIN_DELAY = 30       # segundos
MAX_DELAY = 180      # segundos
JITTER_PCT = 0.30    # ±30 %

# ─────────────────────────────────────────────────────────────────────────────
# Threshold mínimo de saúde para enviar mensagens.
# Instâncias com saúde abaixo são bloqueadas pelo instance_router até se
# recuperarem (saúde só sobe via update_health_scores no fim do dia, com base
# em delivery rate). Valor escolhido junto ao operador: 60 (ontem ban com 52%).
# ─────────────────────────────────────────────────────────────────────────────
MIN_HEALTH_SCORE = 60

# ─────────────────────────────────────────────────────────────────────────────
# Falhas consecutivas — número que bloqueia a instância automaticamente.
# Erros classificados como "no_whatsapp" não contam (problema do lead).
# ─────────────────────────────────────────────────────────────────────────────
MAX_CONSECUTIVE_FAILURES = 5

# ─────────────────────────────────────────────────────────────────────────────
# Horário comercial e janelas
# ─────────────────────────────────────────────────────────────────────────────
BRT = timezone(timedelta(hours=-3))
BUSINESS_START = 8   # hora BRT
BUSINESS_END = 20    # hora BRT (exclusive)

# Cada janela: (start_h, end_h, cumulative_quota_pct)
# Entre uma janela e a próxima existe um intervalo (almoço/jantar) em que o
# worker dorme. A última janela cobre 100 % do daily_limit.
SEND_WINDOWS: list[tuple[float, float, float]] = [
    (8.0, 11.5, 0.33),   # manhã: até 33 % do daily_limit
    (14.0, 17.0, 0.66),  # tarde: até 66 %
    (17.0, 20.0, 1.00),  # noite: até 100 %
]


def _gaussian_delay() -> float:
    """Delay gaussiano entre MIN e MAX com jitter."""
    mu = (MIN_DELAY + MAX_DELAY) / 2
    sigma = (MAX_DELAY - MIN_DELAY) / 6
    base = max(MIN_DELAY, min(MAX_DELAY, random.gauss(mu, sigma)))
    jitter = base * JITTER_PCT * random.uniform(-1, 1)
    return max(1.0, base + jitter)


def _now_brt() -> datetime:
    return datetime.now(timezone.utc).astimezone(BRT)


def _now_hour_decimal(dt: datetime | None = None) -> float:
    """Hora atual BRT em float (ex: 14:30 → 14.5)."""
    now = (dt or datetime.now(timezone.utc)).astimezone(BRT)
    return now.hour + now.minute / 60.0 + now.second / 3600.0


def is_business_hours(dt: datetime | None = None) -> bool:
    """Retorna True se o horário atual (BRT) estiver no intervalo comercial."""
    h = _now_hour_decimal(dt)
    return BUSINESS_START <= h < BUSINESS_END


def seconds_until_business_hours() -> float:
    """Quantos segundos faltam até abrir o horário comercial."""
    now = _now_brt()
    if is_business_hours(now):
        return 0.0
    if now.hour < BUSINESS_START:
        target = now.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
    else:
        target = (now + timedelta(days=1)).replace(
            hour=BUSINESS_START, minute=0, second=0, microsecond=0
        )
    return (target - now).total_seconds()


# ─────────────────────────────────────────────────────────────────────────────
# Janelas — usado quando campaign.use_windows=True
# ─────────────────────────────────────────────────────────────────────────────
def current_window_quota_pct() -> float | None:
    """
    Retorna a fração cumulativa do daily_limit que pode ter sido enviada até
    agora, considerando as janelas. None = fora de qualquer janela ativa
    (intervalo entre janelas, fora do horário comercial).
    """
    h = _now_hour_decimal()
    for start_h, end_h, pct in SEND_WINDOWS:
        if start_h <= h < end_h:
            return pct
    return None


def seconds_until_next_window() -> float:
    """
    Quantos segundos faltam até a próxima janela abrir.
    Se já estamos dentro de uma janela, retorna 0.
    Se já passou da última janela, retorna o tempo até a primeira janela
    do próximo dia útil.
    """
    now = _now_brt()
    h = _now_hour_decimal(now)

    if current_window_quota_pct() is not None:
        return 0.0

    # Procura próxima janela hoje
    for start_h, _end_h, _pct in SEND_WINDOWS:
        if h < start_h:
            target_hour = int(start_h)
            target_minute = int((start_h - target_hour) * 60)
            target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            return max(0.0, (target - now).total_seconds())

    # Já passou da última janela do dia — primeira janela amanhã
    first_start = SEND_WINDOWS[0][0]
    target_hour = int(first_start)
    target_minute = int((first_start - target_hour) * 60)
    target = (now + timedelta(days=1)).replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
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


async def wait_for_next_window() -> float:
    """
    Se estamos numa pausa entre janelas, dorme até a próxima abrir.
    Retorna quantos segundos foram aguardados (útil para logs).
    """
    wait = seconds_until_next_window()
    if wait > 0:
        await asyncio.sleep(wait)
    return wait


def can_send(daily_sent: int, daily_limit: int) -> bool:
    """Verifica se a instância ainda pode enviar hoje."""
    return daily_sent < daily_limit


# ─────────────────────────────────────────────────────────────────────────────
# Classificação de erros — usada pelo worker para decidir penalidade na saúde
# e quando colocar a instância em quarentena automaticamente.
# ─────────────────────────────────────────────────────────────────────────────
_NO_WHATSAPP_TOKENS = (
    "not exists in whatsapp",
    "exists\":false",
    "número não",
    "number not on whatsapp",
    "number does not exist",
    "is not on whatsapp",
)
# Erros onde a mensagem DEFINITIVAMENTE não foi enviada — seguro retentar.
# Apenas falhas de conexão pura: o request nunca chegou ao servidor da Evolution API.
# ReadTimeout É EXCLUÍDO propositalmente: a conexão foi estabelecida e o request
# enviado, então a Evolution API pode ter processado e enviado ao WhatsApp antes
# do timeout. Retentar causaria duplicata confirmada em produção (2026-05-13).
_TRANSIENT_TOKENS = (
    "connecttimeout",    # Timeout ao estabelecer TCP — request nunca enviado
    "connecterror",      # Conexão recusada/falhou — request nunca enviado
    "pooltimeout",       # Pool de conexões esgotado — request nunca enviado
    "remotedisconnected", # Servidor fechou antes de receber — request nunca enviado
)
_SEVERE_TOKENS = (
    "401",
    "stream errored",
    "device_removed",
    "logged out",
    "connection failure",
    "banned",
    "forbidden",
    "blocked",
    "session is closed",
)


def classify_error(error_message: str) -> str:
    """
    Classifica o erro em uma de quatro categorias:
      - "no_whatsapp": número sem WhatsApp (não penaliza instância, exclui do dedup)
      - "transient":   falha de conexão pura — seguro retentar (request nunca enviado)
      - "severe":      ban/sessão derrubada — penalidade alta + quarentena
      - "mild":        outros erros incluindo ReadTimeout — falha permanente, sem retry
    """
    if not error_message:
        return "mild"
    e = error_message.lower()
    if any(t in e for t in _NO_WHATSAPP_TOKENS):
        return "no_whatsapp"
    if any(t in e for t in _TRANSIENT_TOKENS):
        return "transient"
    if any(t in e for t in _SEVERE_TOKENS):
        return "severe"
    return "mild"
