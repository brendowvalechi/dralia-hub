import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin, require_operator
from app.database import get_db
from app.models.instance import Instance, InstanceStatus
from app.models.user import User
from app.schemas.instance import InstanceCreate, InstanceQRCode, InstanceResponse, InstanceUpdate
from app.services import evolution_client

router = APIRouter(prefix="/instances", tags=["instances"])


def _evo_status_to_local(evo_state: str) -> InstanceStatus:
    """Converte estado da Evolution API para nosso enum."""
    mapping = {
        "open": InstanceStatus.connected,
        "connecting": InstanceStatus.disconnected,
        "close": InstanceStatus.disconnected,
    }
    return mapping.get(evo_state.lower(), InstanceStatus.disconnected)


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
@router.get("", response_model=list[InstanceResponse])
async def list_instances(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (await db.execute(select(Instance).order_by(Instance.display_name))).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# GET BY ID
# ---------------------------------------------------------------------------
@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")
    return inst


# ---------------------------------------------------------------------------
# CREATE — registra no banco E cria na Evolution API
# ---------------------------------------------------------------------------
@router.post("", response_model=InstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    body: InstanceCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    # Verifica duplicata
    existing = (
        await db.execute(
            select(Instance).where(Instance.evolution_instance_name == body.evolution_instance_name)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nome de instância já cadastrado")

    # Cria na Evolution API
    try:
        await evolution_client.create_instance(body.evolution_instance_name, body.webhook_url)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro na Evolution API: {exc.response.text}",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Evolution API inacessível: {exc}",
        )

    inst = Instance(
        display_name=body.display_name,
        evolution_instance_name=body.evolution_instance_name,
        daily_limit=body.daily_limit,
        status=InstanceStatus.disconnected,
    )
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


# ---------------------------------------------------------------------------
# UPDATE — apenas campos locais (display_name, daily_limit, status manual)
# ---------------------------------------------------------------------------
@router.put("/{instance_id}", response_model=InstanceResponse)
async def update_instance(
    instance_id: uuid.UUID,
    body: InstanceUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(inst, field, value)
    inst.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(inst)
    return inst


# ---------------------------------------------------------------------------
# DELETE — remove da Evolution API e do banco
# ---------------------------------------------------------------------------
@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    # Remove na Evolution API (best-effort — se já não existir, ignora)
    try:
        await evolution_client.delete_instance(inst.evolution_instance_name)
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass

    await db.delete(inst)
    await db.commit()


# ---------------------------------------------------------------------------
# GET QR CODE — para conectar ao WhatsApp
# ---------------------------------------------------------------------------
@router.get("/{instance_id}/qrcode", response_model=InstanceQRCode)
async def get_qrcode(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    try:
        data = await evolution_client.get_instance_qrcode(inst.evolution_instance_name)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro na Evolution API: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Evolution API inacessível: {exc}")

    # A Evolution API pode retornar o QR em diferentes estruturas dependendo da versão
    qr = (
        data.get("base64")
        or data.get("qrcode", {}).get("base64")
        or data.get("code")
        or (data.get("data") or {}).get("base64")
        or (data.get("data") or {}).get("qrcode", {}).get("base64")
    )
    return InstanceQRCode(
        instance_name=inst.evolution_instance_name,
        qrcode=qr,
        status=inst.status.value,
    )


# ---------------------------------------------------------------------------
# SYNC STATUS — sincroniza estado real da Evolution API com o banco
# ---------------------------------------------------------------------------
@router.post("/{instance_id}/sync", response_model=InstanceResponse)
async def sync_instance_status(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    try:
        data = await evolution_client.get_instance_status(inst.evolution_instance_name)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro na Evolution API: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Evolution API inacessível: {exc}")

    evo_state = data.get("instance", {}).get("state", "close")
    new_status = _evo_status_to_local(evo_state)

    now = datetime.now(timezone.utc)
    if new_status == InstanceStatus.connected and inst.status != InstanceStatus.connected:
        inst.last_connected_at = now
    elif new_status == InstanceStatus.disconnected and inst.status == InstanceStatus.connected:
        inst.last_disconnected_at = now

    inst.status = new_status
    inst.updated_at = now
    await db.commit()
    await db.refresh(inst)
    return inst


# ---------------------------------------------------------------------------
# LOGOUT — desconecta da sessão WhatsApp
# ---------------------------------------------------------------------------
@router.post("/{instance_id}/logout", response_model=InstanceResponse)
async def logout_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    try:
        await evolution_client.logout_instance(inst.evolution_instance_name)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro na Evolution API: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Evolution API inacessível: {exc}")

    inst.status = InstanceStatus.disconnected
    inst.last_disconnected_at = datetime.now(timezone.utc)
    inst.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(inst)
    return inst


# ---------------------------------------------------------------------------
# RESTART
# ---------------------------------------------------------------------------
@router.post("/{instance_id}/restart", response_model=InstanceResponse)
async def restart_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    inst = await db.get(Instance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instância não encontrada")

    try:
        await evolution_client.restart_instance(inst.evolution_instance_name)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro na Evolution API: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Evolution API inacessível: {exc}")

    inst.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(inst)
    return inst
