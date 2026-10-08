import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.common.db import make_sessionmaker

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
KYC = SAMPLES / "client_kyc"


def load(path: Path):
    return json.loads(path.read_text())


@pytest.fixture
def onboarding_ir() -> dict:
    """Document-led sample IR, version 3 (mid-review, has stories)."""
    return copy.deepcopy(_cached(SAMPLES / "ir_client_onboarding.json"))


@pytest.fixture
def patch_example() -> dict:
    return copy.deepcopy(_cached(SAMPLES / "patch_example.json"))


_cache: dict[Path, object] = {}


def _cached(path: Path):
    if path not in _cache:
        _cache[path] = load(path)
    return _cache[path]


# ---------------------------------------------------------------- database
# DB tests run against a throwaway database created on the server named by RS_DATABASE_URL, and skip without it.
# Locally: `docker compose up -d postgres` and `RS_DATABASE_URL=postgresql+asyncpg://rs:rs@localhost:5432/rs`.
BASE_URL = os.environ.get("RS_DATABASE_URL")

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


@pytest.fixture
async def tx_sessionmaker(engine):
    """Sessions that share one outer transaction, rolled back after the test. Their commits become savepoints, so
    tests can use fixed sample ids (and never need to delete from the append-only audit_log)."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        yield async_sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        await outer.rollback()
