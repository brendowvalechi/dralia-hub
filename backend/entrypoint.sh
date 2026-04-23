#!/bin/sh
# Entrypoint do container backend/worker.
# Aguarda o PostgreSQL ficar disponível, aplica migrações e inicia o serviço.

set -e

echo "[entrypoint] Aguardando PostgreSQL..."
until python -c "
import asyncio, asyncpg, os, sys

async def check():
    url = os.environ['DATABASE_URL'].replace('postgresql://', '')
    try:
        conn = await asyncpg.connect('postgresql://' + url)
        await conn.close()
    except Exception as e:
        print(f'DB não disponível: {e}', file=sys.stderr)
        sys.exit(1)

asyncio.run(check())
" 2>/dev/null; do
  echo "[entrypoint] PostgreSQL não disponível — aguardando 2s..."
  sleep 2
done

echo "[entrypoint] PostgreSQL disponível."

# Aplica migrações (só se for o serviço de API, não o worker)
if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "[entrypoint] Aplicando migrações Alembic..."
  alembic upgrade head
  echo "[entrypoint] Migrações aplicadas."
fi

echo "[entrypoint] Iniciando: $@"
exec "$@"
