# Dra Lia Hub

Plataforma de automação e disparo de mensagens WhatsApp.

## Stack

- **Backend**: FastAPI + PostgreSQL + Celery + Redis
- **Frontend**: React (Vite)
- **Infra**: Docker + Nginx

## Como rodar (dev)

```bash
cp .env.example .env
docker-compose -f docker-compose.dev.yml up --build
```

A API estará disponível em `http://localhost:8000`.
