"""
Cliente HTTP para a Evolution API.

Documentação: https://doc.evolution-api.com
Todos os métodos levantam httpx.HTTPStatusError em caso de erro HTTP.
"""
import httpx

from app.config import settings

_TIMEOUT = 20.0


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.EVOLUTION_API_URL,
        headers={"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"},
        timeout=_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Instâncias
# ---------------------------------------------------------------------------
async def create_instance(name: str, webhook_url: str | None = None) -> dict:
    """Cria uma nova instância na Evolution API."""
    payload: dict = {
        "instanceName": name,
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
    }
    if webhook_url:
        payload["webhook"] = {"url": webhook_url, "byEvents": False, "base64": False}

    async with _client() as c:
        r = await c.post("/instance/create", json=payload)
        r.raise_for_status()
        return r.json()


async def get_instance_status(name: str) -> dict:
    """Retorna connectionStatus da instância."""
    async with _client() as c:
        r = await c.get(f"/instance/connectionState/{name}")
        r.raise_for_status()
        return r.json()


async def get_instance_qrcode(name: str) -> dict:
    """Retorna o QR code atual da instância."""
    async with _client() as c:
        r = await c.get(f"/instance/connect/{name}")
        r.raise_for_status()
        return r.json()


async def logout_instance(name: str) -> dict:
    """Desconecta a instância (logout do WhatsApp)."""
    async with _client() as c:
        r = await c.delete(f"/instance/logout/{name}")
        r.raise_for_status()
        return r.json()


async def delete_instance(name: str) -> dict:
    """Remove a instância da Evolution API."""
    async with _client() as c:
        r = await c.delete(f"/instance/delete/{name}")
        r.raise_for_status()
        return r.json()


async def restart_instance(name: str) -> dict:
    """Reinicia a instância."""
    async with _client() as c:
        r = await c.put(f"/instance/restart/{name}")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Envio de mensagens
# ---------------------------------------------------------------------------
async def send_text(instance_name: str, phone: str, text: str) -> dict:
    """
    Envia mensagem de texto simples.
    phone: número no formato E.164 sem o '+' (ex: 5511999999999)
    """
    number = phone.lstrip("+")
    async with _client() as c:
        r = await c.post(
            f"/message/sendText/{instance_name}",
            json={"number": number, "text": text},
        )
        r.raise_for_status()
        return r.json()


async def send_media(
    instance_name: str,
    phone: str,
    media_url: str,
    media_type: str,
    caption: str = "",
) -> dict:
    """
    Envia mídia (image/video/audio/document).
    media_type: 'image' | 'video' | 'audio' | 'document'
    """
    number = phone.lstrip("+")
    async with _client() as c:
        r = await c.post(
            f"/message/sendMedia/{instance_name}",
            json={
                "number": number,
                "mediatype": media_type,
                "media": media_url,
                "caption": caption,
            },
        )
        r.raise_for_status()
        return r.json()


async def send_audio_ptt(
    instance_name: str,
    phone: str,
    audio_url: str,
) -> dict:
    """
    Envia áudio como mensagem de voz (PTT — Push To Talk).

    O áudio NÃO aparece como "encaminhado" pois usa o endpoint sendWhatsAppAudio.
    A Evolution API re-codifica o arquivo para OGG/Opus com ffmpeg (encoding=true),
    então qualquer formato de entrada (MP3, WAV, M4A, etc.) é aceito.

    audio_url: URL acessível pelo container da Evolution API
               (ex: http://backend:8000/media/arquivo.mp3)
    """
    number = phone.lstrip("+")
    async with _client() as c:
        r = await c.post(
            f"/message/sendWhatsAppAudio/{instance_name}",
            json={"number": number, "audio": audio_url, "encoding": True},
        )
        r.raise_for_status()
        return r.json()


async def send_typing(instance_name: str, phone: str, duration_ms: int = 2000) -> None:
    """Simula 'digitando…' por duration_ms milissegundos (anti-ban)."""
    number = phone.lstrip("+")
    async with _client() as c:
        r = await c.post(
            f"/chat/sendPresence/{instance_name}",
            json={"number": number, "options": {"presence": "composing", "delay": duration_ms}},
        )
        _ = r


async def send_recording(instance_name: str, phone: str, duration_ms: int = 3000) -> None:
    """Simula 'gravando áudio…' por duration_ms milissegundos (anti-ban para PTT)."""
    number = phone.lstrip("+")
    async with _client() as c:
        r = await c.post(
            f"/chat/sendPresence/{instance_name}",
            json={"number": number, "options": {"presence": "recording", "delay": duration_ms}},
        )
        _ = r
