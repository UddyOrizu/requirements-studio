"""DB tests run against a throwaway database created on the server named by RS_DATABASE_URL.

Skipped when RS_DATABASE_URL is unset. Locally: `docker compose up -d postgres` and
`RS_DATABASE_URL=postgresql+asyncpg://rs:rs@localhost:5432/rs uv run pytest`.
"""
import os
import subprocess
import sys
import uuid

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from services.common.db import make_sessionmaker
from tests.conftest import ROOT

BASE_URL = os.environ.get("RS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="RS_DATABASE_URL not set")


def alembic(url: str, *args: str) -> None:
    env = {**os.environ, "RS_DATABASE_URL": url}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        pytest.fail(f"alembic {' '.join(args)} failed:\n{r.stderr[-4000:]}", pytrace=False)


async def _admin(sql: str) -> None:
    url = make_url(BASE_URL).set(drivername="postgresql")
    conn = await asyncpg.connect(url.render_as_string(hide_password=False))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def db_url():
    if not BASE_URL:
        pytest.skip("RS_DATABASE_URL not set")
    name = f"rs_test_{uuid.uuid4().hex[:12]}"
    await _admin(f'CREATE DATABASE "{name}"')
    url = make_url(BASE_URL).set(database=name).render_as_string(hide_password=False)
    # Up, down and up again: proves the downgrade is complete and the upgrade is repeatable.
    alembic(url, "upgrade", "head")
    alembic(url, "downgrade", "base")
    alembic(url, "upgrade", "head")
    yield url
    await _admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
async def engine(db_url):
    eng = create_async_engine(db_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine):
    return make_sessionmaker(engine)
