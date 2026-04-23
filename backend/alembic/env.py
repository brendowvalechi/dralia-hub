import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importa config da aplicação para pegar DATABASE_URL
from app.config import settings

# Importa todos os models para que o Alembic os detecte
import app.models  # noqa: F401
from app.database import Base

# Configuração do arquivo alembic.ini
config = context.config

# Configura a URL dinamicamente a partir das variáveis de ambiente
# Converte postgresql:// → postgresql+asyncpg:// para o engine async
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", db_url)

# Configura logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata dos models para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Roda migrações em modo offline (sem conexão ativa)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# Tabelas gerenciadas pela Evolution API (Prisma) — Alembic deve ignorá-las
_EVOLUTION_TABLES = {
    "Template", "Media", "Typebot", "Proxy", "TypebotSetting", "Rabbitmq",
    "IntegrationSession", "OpenaiSetting", "FlowiseSetting", "Instance",
    "Message", "Sqs", "EvolutionBotSetting", "Setting", "_prisma_migrations",
    "MessageUpdate", "Label", "Websocket", "Session", "IsOnWhatsapp",
    "OpenaiBot", "OpenaiCreds", "Pusher", "Contact", "Webhook", "EvolutionBot",
    "Chatwoot", "Dify", "DifySetting", "Chat", "Flowise",
}


def _include_object(obj, name, type_, reflected, compare_to):
    """Exclui tabelas da Evolution API do autogenerate do Alembic."""
    if type_ == "table" and name in _EVOLUTION_TABLES:
        return False
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Cria engine async e roda migrações."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Roda migrações em modo online (com conexão ativa)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
