from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "dralia",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.campaign_worker", "app.tasks.scheduled"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,      # um job por vez por worker
    task_acks_late=True,               # só confirma após conclusão
    broker_connection_retry_on_startup=False,
    broker_transport_options={"socket_timeout": 3, "socket_connect_timeout": 3},
    beat_schedule={
        # Zera daily_sent todo dia à meia-noite (horário de Brasília)
        "reset-daily-sent": {
            "task": "scheduled.reset_daily_sent",
            "schedule": crontab(hour=0, minute=0),
        },
        # Avança warm-up das instâncias conectadas às 00:05
        "advance-warmup": {
            "task": "scheduled.advance_warmup",
            "schedule": crontab(hour=0, minute=5),
        },
        # Recalcula health_score às 23:55 (fim do dia de trabalho)
        "update-health-scores": {
            "task": "scheduled.update_health_scores",
            "schedule": crontab(hour=23, minute=55),
        },
        # Recalcula contagem dos segmentos a cada hora
        "refresh-segment-counts": {
            "task": "scheduled.refresh_segment_counts",
            "schedule": crontab(minute=0),
        },
    },
)
