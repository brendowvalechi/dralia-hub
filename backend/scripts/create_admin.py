"""
Script para criar um usuário administrador.

Uso:
    cd backend
    python scripts/create_admin.py admin@example.com senha123
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.user import User, UserRole
from app.services.auth_service import hash_password

DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


async def create_admin(email: str, password: str) -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"Usuário '{email}' já existe.")
            await engine.dispose()
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin '{email}' criado com sucesso. ID: {user.id}")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python scripts/create_admin.py <email> <senha>")
        sys.exit(1)

    asyncio.run(create_admin(sys.argv[1], sys.argv[2]))
