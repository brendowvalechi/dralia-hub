"""
Endpoint para upload de arquivos de mídia (áudio, imagem, etc.).

Os arquivos ficam em /app/media/ (volume persistente) e são servidos
via StaticFiles em /media/{filename}.

A Evolution API acessa os arquivos internamente via http://backend:8000/media/{filename},
garantindo que não há dependência de URL pública durante o envio.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import require_operator
from app.models.user import User

router = APIRouter(prefix="/media", tags=["media"])

MEDIA_DIR = Path("/app/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Formatos aceitos
ALLOWED_AUDIO = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".amr", ".opus"}
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO = {".mp4", ".mov", ".avi", ".mkv"}
ALLOWED_DOCUMENT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}

ALL_ALLOWED = ALLOWED_AUDIO | ALLOWED_IMAGE | ALLOWED_VIDEO | ALLOWED_DOCUMENT

MAX_SIZE_MB = 50


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    _: User = Depends(require_operator),
):
    """
    Faz upload de um arquivo de mídia e retorna a URL interna para uso em campanhas.

    Retorna:
    - `url`: URL interna acessível pelo container da Evolution API
    - `media_type`: tipo de mídia detectado ('audio', 'image', 'video', 'document')
    - `filename`: nome do arquivo salvo
    """
    original = file.filename or "file"
    suffix = Path(original).suffix.lower()

    if suffix not in ALL_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato não suportado: {suffix}. Formatos aceitos: {', '.join(sorted(ALL_ALLOWED))}",
        )

    content = await file.read()

    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo muito grande ({size_mb:.1f} MB). Máximo: {MAX_SIZE_MB} MB",
        )

    # Nome único para evitar colisões
    unique_name = f"{uuid.uuid4().hex}{suffix}"
    dest = MEDIA_DIR / unique_name

    dest.write_bytes(content)

    # Detecta tipo
    if suffix in ALLOWED_AUDIO:
        media_type = "audio"
    elif suffix in ALLOWED_IMAGE:
        media_type = "image"
    elif suffix in ALLOWED_VIDEO:
        media_type = "video"
    else:
        media_type = "document"

    # URL interna (acessível pelo container evolution-api via rede Docker)
    internal_url = f"http://backend:8000/media/{unique_name}"

    return {
        "url": internal_url,
        "media_type": media_type,
        "filename": unique_name,
        "original_filename": original,
        "size_mb": round(size_mb, 2),
    }
