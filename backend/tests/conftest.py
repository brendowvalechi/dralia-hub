"""
Configuração dos testes.

Testes unitários (test_spintax, test_warmup) não usam banco.
Testes de integração (test_auth, test_leads, test_campaigns) usam PostgreSQL real
via DATABASE_URL no ambiente — ou são marcados com pytest.mark.integration e pulados
se não houver banco disponível.
"""
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# URL de banco para testes — padrão: banco local de dev
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://dralia:dralia@localhost:5432/dralia_test",
)

_engine = None
_SessionLocal = None


def get_test_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_async_engine(TEST_DB_URL, echo=False)
        _SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine, _SessionLocal


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de banco (opt-in via fixture, não autouse)
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    from app.database import Base
    engine, _ = get_test_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception as e:
        pytest.skip(f"Banco de teste indisponível: {e}")
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    _, SessionLocal = get_test_engine()
    async with SessionLocal() as session:
        yield session
        # Rollback para garantir isolamento entre testes
        await session.rollback()


@pytest_asyncio.fixture
async def client(setup_test_db) -> AsyncGenerator[AsyncClient, None]:
    from app.database import get_db
    from app.main import app

    _, SessionLocal = get_test_engine()

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession):
    from app.models.user import User, UserRole
    from app.services.auth_service import hash_password

    # Limpa usuário de teste anterior
    from sqlalchemy import select, delete
    await db.execute(delete(User).where(User.email == "admin@test.com"))
    await db.commit()

    user = User(
        email="admin@test.com",
        password_hash=hash_password("admin123"),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, admin_user) -> str:
    resp = await client.post("/auth/login", json={"email": "admin@test.com", "password": "admin123"})
    return resp.json()["access_token"]


@pytest_asyncio.fixture
def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
