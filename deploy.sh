#!/bin/bash
# ============================================================
# deploy.sh — Script de deploy para o VPS (Ubuntu 24.04)
# Uso: bash deploy.sh
# ============================================================
set -e

echo ""
echo "======================================================"
echo "  Dra Lia Hub — Deploy no VPS"
echo "======================================================"

# Instala Docker se não tiver
if ! command -v docker &>/dev/null; then
  echo "[1/6] Instalando Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
else
  echo "[1/6] Docker já instalado — OK"
fi

# Instala Git se não tiver
if ! command -v git &>/dev/null; then
  echo "[2/6] Instalando Git..."
  apt-get install -y git
else
  echo "[2/6] Git já instalado — OK"
fi

echo "[3/6] Verificando arquivo .env..."
if [ ! -f ".env" ]; then
  echo ""
  echo "  ERRO: arquivo .env não encontrado!"
  echo "  Copie o .env.example e preencha as variáveis:"
  echo "    cp .env.example .env && nano .env"
  echo ""
  exit 1
fi

echo "[4/6] Construindo e subindo containers..."
docker compose up -d --build

echo "[5/6] Aguardando banco de dados ficar pronto..."
sleep 15

echo "[6/6] Aplicando migrações do banco..."
docker compose exec -T backend alembic upgrade head

echo "[+] Reiniciando nginx para reconectar aos novos containers..."
docker compose restart nginx

echo ""
echo "======================================================"
echo "  DEPLOY CONCLUÍDO!"
echo ""
echo "  Acesse o painel em: http://82.197.65.66"
echo ""
echo "  Para criar o usuário admin:"
echo "  docker compose exec backend bash -c \\"
echo "    \"PYTHONPATH=/app python scripts/create_admin.py admin@dralia.com suasenha\""
echo ""
echo "  Para ver os logs:"
echo "  docker compose logs -f"
echo "======================================================"
