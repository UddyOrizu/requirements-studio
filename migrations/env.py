import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import services.common.outbox  # noqa: F401  (register mapped tables)
import services.gaps.db  # noqa: F401
import services.ideas.db  # noqa: F401
import services.identity_audit.db  # noqa: F401
import services.intake.db  # noqa: F401
import services.interviewer.db  # noqa: F401
import services.ir_store.db  # noqa: F401
import services.llm_gateway.db  # noqa: F401
from services.common.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

DATABASE_URL = os.environ.get("RS_DATABASE_URL", "postgresql+asyncpg://rs:rs@localhost:5432/rs")
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Tables without ORM classes yet (most of docs/04 until their phase) exist only in migrations.
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
