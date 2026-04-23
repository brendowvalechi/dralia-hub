# P3F Hub — Plataforma de Marketing via WhatsApp

Plataforma SaaS para disparo massivo de mensagens WhatsApp com motor anti-ban,
spintax, warm-up de instâncias e dashboard em tempo real.

---

## Arquitetura

```
Internet
   │
  [Nginx :80/:443]
   ├─ /api/*          → FastAPI (backend:8000)
   ├─ /grafana/       → Grafana (grafana:3000)
   └─ /*              → React SPA (dist/)

[FastAPI]
   ├─ Auth JWT
   ├─ CRUD: Leads, Instâncias, Campanhas, Segmentos, Usuários
   ├─ Dashboard + /metrics (Prometheus)
   └─ Webhook Evolution API

[Celery Worker]
   └─ campaign_worker.run_campaign
       ├─ Instance Router (round-robin ponderado por health_score + DDD)
       ├─ Spintax Engine ({a|b} + {{variáveis}})
       └─ Anti-ban Engine (delays gaussianos 15-90s, horário comercial BRT)

[Celery Beat — tarefas agendadas]
   ├─ 00:00 — reset_daily_sent (zera contadores diários)
   ├─ 00:05 — advance_warmup (avança protocolo 30 dias)
   ├─ 23:55 — update_health_scores (recalcula saúde das instâncias)
   └─ :00   — refresh_segment_counts (recalcula lead_count por hora)

[Evolution API]  ←→  WhatsApp
[PostgreSQL 16]  ←→  Banco principal
[Redis 7]        ←→  Broker Celery + cache Evolution API
[Prometheus]     ←→  Coleta métricas do /metrics
[Grafana]        ←→  Dashboards de monitoramento
```

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2.0 async |
| Banco | PostgreSQL 16 |
| Fila | Redis 7 + Celery 5 |
| WhatsApp | Evolution API (self-hosted) |
| Frontend | React + TypeScript + Vite + Tailwind CSS v4 |
| Infra | Docker Compose + Nginx |
| Monitoramento | Prometheus + Grafana |

---

## Pré-requisitos

- Docker 24+ e Docker Compose v2
- (Produção) Servidor Linux com porta 80/443 aberta e domínio configurado

---

## Início rápido (desenvolvimento)

```bash
# 1. Clone e configure o ambiente
git clone <repo>
cd dralia-hub
cp .env.example .env
# Edite .env com suas senhas

# 2. Suba todos os serviços
docker-compose -f docker-compose.dev.yml up --build

# 3. Crie o admin
docker-compose -f docker-compose.dev.yml exec backend \
  python scripts/create_admin.py admin@dralia.com admin123

# 4. Acesse
# API docs: http://localhost:8000/docs
# Frontend: http://localhost:5173 (se rodar npm run dev)
```

---

## Deploy em produção

### 1. Preparar o servidor

```bash
# Ubuntu 22.04 LTS recomendado
apt-get update && apt-get install -y docker.io docker-compose-v2
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env  # Preencha todas as senhas e chaves
```

Variáveis obrigatórias:
- `POSTGRES_PASSWORD` — senha forte para o banco
- `JWT_SECRET_KEY` — gere com `python -c "import secrets; print(secrets.token_hex(32))"`
- `EVOLUTION_API_KEY` — chave da Evolution API
- `GRAFANA_PASSWORD` — senha do Grafana

### 3. Build e subida

```bash
# Build do frontend
cd frontend && npm install && npm run build && cd ..

# Subir todos os serviços em produção
docker-compose up -d --build

# Criar admin
docker-compose exec backend python scripts/create_admin.py admin@empresa.com SENHA_FORTE
```

### 4. Verificar saúde do sistema

```bash
./scripts/healthcheck.sh http://localhost:8000
```

### 5. Configurar SSL (obrigatório em produção)

```bash
chmod +x scripts/setup_ssl.sh
./scripts/setup_ssl.sh SEU_DOMINIO.COM SEU_EMAIL@empresa.com
```

Após obter o certificado, edite `nginx/nginx.conf`:
- Descomente o bloco `server { listen 80; return 301 ... }` para redirect HTTP→HTTPS
- Descomente as linhas `listen 443 ssl`, `ssl_certificate`, `ssl_certificate_key`
- Atualize `server_name` para seu domínio

```bash
docker-compose restart nginx
```

### 6. Configurar renovação automática de SSL

```bash
# Adicione ao cron (crontab -e):
0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/SEU_DOMINIO/*.pem /path/to/dralia-hub/nginx/ssl/ && \
  docker-compose -f /path/to/dralia-hub/docker-compose.yml restart nginx
```

---

## Monitoramento

- **Grafana**: `http://SEU_DOMINIO/grafana/` (user/senha configurados no `.env`)
- **Prometheus**: acesso interno via `http://prometheus:9090`

Métricas disponíveis em `/metrics`:
- `p3f_leads_total{status}` — leads por status
- `p3f_instances_total{status}` — instâncias por status
- `p3f_instance_health_avg` — health score médio
- `p3f_campaigns_total{status}` — campanhas por status
- `p3f_messages_total{status}` — mensagens por status
- `p3f_delivery_rate_pct` — taxa de entrega global

---

## Gerenciamento de instâncias WhatsApp

### Conectar uma nova instância

1. Acesse **Instâncias** no painel
2. Clique em **Nova instância** e preencha:
   - Nome de exibição (ex: "WhatsApp Principal")
   - Nome na Evolution API (ex: "wp-principal") — sem espaços
   - Limite diário de mensagens
3. Clique em **QR Code** (ícone) na instância criada
4. Escaneie o QR Code com o WhatsApp → Aparelhos conectados
5. Clique em **Já escaneei** para sincronizar o status

### Warm-up de instâncias novas

Novas instâncias passam por 30 dias de protocolo de warm-up automático:

| Dias | Limite diário |
|------|-------------|
| 1-3  | 20 msgs     |
| 4-7  | 50 msgs     |
| 8-14 | 100 msgs    |
| 15-21| 200 msgs    |
| 22-30| 300 msgs    |
| 31+  | Configurado |

O **health score** (0-100) reflete a taxa de entrega. Instâncias com score baixo recebem menos tráfego pelo roteador.

---

## Motor Anti-ban

- Delays gaussianos de 15-90 segundos com jitter ±30% entre mensagens
- Simulação de "digitando..." antes de cada envio
- Respeito a horário comercial BRT (8h-20h)
- Roteamento round-robin ponderado por health_score
- Afinidade de DDD: leads e instâncias do mesmo DDD são priorizados

---

## Spintax

Suporte a randomização de mensagens e variáveis de lead:

```
{Olá|Oi|E aí}, {{nome}}! 
Temos uma {oferta|promoção} {especial|exclusiva} para você.
```

Variáveis disponíveis: `{{nome}}`, `{{phone}}`, e qualquer campo em `custom_fields` do lead.

---

## Segmentos

Filtre leads para campanhas direcionadas:
- **Por tags**: leads que tenham qualquer tag da lista
- **Por status**: active, inactive

Os contadores são recalculados automaticamente a cada hora pelo Celery Beat.

---

## Testes

```bash
cd backend

# Testes unitários (sem banco, rápido)
venv/Scripts/python.exe -m pytest tests/test_spintax.py tests/test_warmup.py -v

# Testes de integração (requer PostgreSQL)
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dralia_test \
  venv/Scripts/python.exe -m pytest tests/ -v

# Load test (requer locust e API rodando)
pip install locust
locust -f scripts/load_test.py --host=http://localhost:8000
```

---

## Seed de dados para teste

```bash
# Cria 500 leads aleatórios
python scripts/seed_leads.py --count 500 --url http://localhost:8000 \
  --email admin@dralia.com --password admin123
```

---

## Estrutura do projeto

```
dralia-hub/
├── backend/
│   ├── app/
│   │   ├── api/          # Routers FastAPI (auth, leads, campaigns, instances,
│   │   │                 #   dashboard, webhooks, segments, users, metrics)
│   │   ├── models/       # SQLAlchemy ORM (user, lead, campaign, instance,
│   │   │                 #   message, segment)
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Lógica de negócio (auth, evolution, antiban,
│   │   │                 #   spintax, warmup, instance_router)
│   │   └── tasks/        # Celery (campaign_worker, scheduled)
│   ├── alembic/          # Migrations do banco
│   ├── scripts/          # Utilitários (create_admin, seed_leads)
│   ├── tests/            # pytest (unitários + integração)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── api/          # Cliente axios + funções de API
│   │   ├── components/   # Layout, Sidebar, ProtectedRoute, QRCodeModal
│   │   ├── contexts/     # AuthContext, ToastContext
│   │   ├── pages/        # Dashboard, Leads, Instances, Campaigns,
│   │   │                 #   Segments, Users, Login
│   │   └── types/        # TypeScript interfaces
│   └── dist/             # Build de produção (servido pelo nginx)
├── nginx/
│   └── nginx.conf        # Rate limiting, SSL-ready, SPA routing, Grafana proxy
├── monitoring/
│   ├── prometheus.yml    # Scrape config
│   └── grafana/
│       └── provisioning/ # Datasource automático
├── scripts/
│   ├── setup_ssl.sh      # Certbot Let's Encrypt
│   ├── healthcheck.sh    # Verifica serviços pré go-live
│   ├── load_test.py      # Locust load test
│   └── seed_leads.py     # Popula leads de teste
├── docker-compose.yml    # Produção (9 serviços)
├── docker-compose.dev.yml# Desenvolvimento
└── .env.example
```

---

## Permissões de usuário

| Papel | Acesso |
|-------|--------|
| `admin` | Tudo — incluindo criar/excluir instâncias e usuários |
| `operator` | Criar/editar leads, campanhas, segmentos; lançar/pausar campanhas |
| `viewer` | Apenas leitura (dashboard, listas) |

---

## LGPD / Privacidade

- Opt-out via keyword "SAIR" na resposta → status `opted_out` automático
- Endpoint `POST /leads/{id}/optout` para opt-out manual
- Exclusão definitiva via `DELETE /leads/{id}`
- Dados de leads não são compartilhados com terceiros além da Evolution API

---

## Manutenção

```bash
# Ver logs em tempo real
docker-compose logs -f backend
docker-compose logs -f celery-worker

# Reiniciar um serviço específico
docker-compose restart celery-worker

# Zerar daily_sent manualmente (normalmente feito pelo Beat às 00:00)
docker-compose exec celery-worker celery -A app.celery_app call scheduled.reset_daily_sent

# Backup do banco
docker-compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup_$(date +%Y%m%d).sql

# Restaurar backup
docker-compose exec -T postgres psql -U $POSTGRES_USER $POSTGRES_DB < backup_20250101.sql
```
