# ── stage 1: dependências ──────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── stage 2: imagem final ──────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copia pacotes instalados do stage anterior
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copia código da aplicação
COPY . .

# Cria usuário não-root e torna entrypoint executável
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app \
    && chmod +x /app/entrypoint.sh

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["/app/entrypoint.sh"]

# Comando padrão (API). O compose sobrescreve para worker/beat.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
