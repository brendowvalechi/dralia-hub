import io
import uuid
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_operator
from app.database import get_db
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.message import Message
from app.models.user import User
from app.schemas.lead import (
    ImportResult,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)

router = APIRouter(prefix="/leads", tags=["leads"])

OPT_OUT_KEYWORDS = {"sair", "stop", "cancelar", "descadastrar", "optout", "opt-out"}


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status: LeadStatus | None = None,
    tag: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Lead)

    if status:
        q = q.where(Lead.status == status)
    if tag:
        q = q.where(Lead.tags.contains([tag]))
    if search:
        pattern = f"%{search}%"
        q = q.where(Lead.name.ilike(pattern) | Lead.phone.ilike(pattern))

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    q = q.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return LeadListResponse(total=total, page=page, page_size=page_size, items=list(rows))


# ---------------------------------------------------------------------------
# LIST TAGS — todas as tags distintas dos leads
# ---------------------------------------------------------------------------
@router.get("/tags", response_model=list[str])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        text("SELECT DISTINCT jsonb_array_elements_text(tags) AS tag FROM leads WHERE tags != '[]'::jsonb ORDER BY tag")
    )
    return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# GET BY ID
# ---------------------------------------------------------------------------
@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")
    return lead


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    existing = (await db.execute(select(Lead).where(Lead.phone == body.phone))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Telefone já cadastrado")

    lead = Lead(
        phone=body.phone,
        name=body.name,
        email=body.email,
        tags=body.tags,
        custom_fields=body.custom_fields,
        source=body.source,
        notes=body.notes,
        opt_in_date=datetime.now(timezone.utc),
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")

    data = body.model_dump(exclude_unset=True)

    # Opt-out automático ao mudar status
    if data.get("status") == LeadStatus.opted_out and lead.status != LeadStatus.opted_out:
        data["opt_out_date"] = datetime.now(timezone.utc)

    for field, value in data.items():
        setattr(lead, field, value)

    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# DELETE (LGPD — exclusão de dados)
# ---------------------------------------------------------------------------
@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")
    await db.delete(lead)
    await db.commit()


# ---------------------------------------------------------------------------
# LAST MESSAGE — última mensagem enviada ao lead
# ---------------------------------------------------------------------------
@router.get("/{lead_id}/last-message")
async def get_lead_last_message(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")

    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id)
        .order_by(Message.sent_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        return {"found": False}

    return {
        "found": True,
        "content": (msg.content or "")[:300],
        "sent_at": msg.sent_at,
        "status": msg.status,
        "campaign_id": str(msg.campaign_id) if msg.campaign_id else None,
    }


# ---------------------------------------------------------------------------
# OPT-OUT via keyword (chamado pelo webhook da Evolution API)
# ---------------------------------------------------------------------------
@router.post("/optout/keyword", status_code=status.HTTP_200_OK)
async def optout_by_keyword(
    phone: str,
    message: str,
    db: AsyncSession = Depends(get_db),
):
    """Recebe mensagem de opt-out enviada pelo usuário via WhatsApp."""
    if message.strip().lower() not in OPT_OUT_KEYWORDS:
        return {"opted_out": False}

    lead = (await db.execute(select(Lead).where(Lead.phone == phone))).scalar_one_or_none()
    if not lead:
        return {"opted_out": False}

    lead.status = LeadStatus.opted_out
    lead.opt_out_date = datetime.now(timezone.utc)
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"opted_out": True, "lead_id": str(lead.id)}


# ---------------------------------------------------------------------------
# IMPORT CSV / XLSX
# ---------------------------------------------------------------------------
@router.post("/import", response_model=ImportResult)
async def import_leads(
    file: UploadFile = File(...),
    update_existing: bool = Query(False, description="Atualiza leads existentes pelo telefone"),
    group: str | None = Query(None, description="Tag de grupo a aplicar em todos os leads importados"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """
    Importa leads de um arquivo CSV ou XLSX.

    Colunas obrigatórias: `phone`
    Colunas opcionais: `name`, `email`, `tags` (separadas por vírgula), `notes`, e qualquer
    outra coluna extra (vai para `custom_fields`).
    """
    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_csv(io.StringIO(content.decode("utf-8", errors="replace")), dtype=str)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao ler arquivo: {exc}")

    if "phone" not in df.columns:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Coluna 'phone' obrigatória")

    KNOWN_COLS = {"phone", "name", "email", "tags", "notes"}
    extra_cols = [c for c in df.columns if c not in KNOWN_COLS]

    created = updated = skipped = 0
    errors: list[str] = []

    for i, row in df.iterrows():
        row_num = int(i) + 2  # cabeçalho é linha 1
        raw_phone = str(row.get("phone", "")).strip()
        if not raw_phone or raw_phone == "nan":
            errors.append(f"Linha {row_num}: telefone vazio")
            skipped += 1
            continue

        # Normaliza para E.164 básico
        phone = raw_phone if raw_phone.startswith("+") else f"+{raw_phone}"
        digits = phone[1:]
        if not digits.isdigit() or not (7 <= len(digits) <= 15):
            errors.append(f"Linha {row_num}: telefone inválido '{raw_phone}'")
            skipped += 1
            continue

        # Tags
        raw_tags = str(row.get("tags", "")).strip()
        tags = [t.strip() for t in raw_tags.split(",") if t.strip() and raw_tags != "nan"]
        if group and group not in tags:
            tags.append(group)

        # Custom fields
        custom_fields: dict = {}
        for col in extra_cols:
            val = row.get(col)
            if val and str(val) != "nan":
                custom_fields[col] = str(val)

        name = str(row.get("name", "")).strip() or None
        if name == "nan":
            name = None
        email = str(row.get("email", "")).strip() or None
        if email == "nan":
            email = None
        notes = str(row.get("notes", "")).strip() or None
        if notes == "nan":
            notes = None

        existing = (await db.execute(select(Lead).where(Lead.phone == phone))).scalar_one_or_none()

        if existing:
            if update_existing:
                if name:
                    existing.name = name
                if email:
                    existing.email = email
                if tags:
                    existing.tags = list({*existing.tags, *tags})
                elif group and group not in existing.tags:
                    existing.tags = [*existing.tags, group]
                if custom_fields:
                    existing.custom_fields = {**existing.custom_fields, **custom_fields}
                if notes:
                    existing.notes = notes
                existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            elif group and group not in existing.tags:
                # Always apply group tag even when not update_existing
                existing.tags = [*existing.tags, group]
                existing.updated_at = datetime.now(timezone.utc)
                skipped += 1
            else:
                skipped += 1
        else:
            lead = Lead(
                phone=phone,
                name=name,
                email=email,
                tags=tags,
                custom_fields=custom_fields,
                notes=notes,
                source=LeadSource.import_,
                opt_in_date=datetime.now(timezone.utc),
            )
            db.add(lead)
            created += 1

    await db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors[:50])
