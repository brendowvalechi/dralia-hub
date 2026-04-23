from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine
from app.api import auth, leads, campaigns, instances, dashboard, webhooks, segments, users, metrics
from app.api import media as media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"WARNING: database not reachable: {e}")
    yield


app = FastAPI(title="Dra Lia Hub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(campaigns.router)
app.include_router(instances.router)
app.include_router(dashboard.router)
app.include_router(webhooks.router)
app.include_router(segments.router)
app.include_router(users.router)
app.include_router(metrics.router)
app.include_router(media_router.router)

# Serve uploaded media files — acessível também pelo container evolution-api
_media_dir = Path("/app/media")
_media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
