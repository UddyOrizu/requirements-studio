#!/usr/bin/env python3
"""Create (if missing) and migrate the database the UI tests run against.

Usage: RS_DATABASE_URL=postgresql+asyncpg://…/rs_e2e uv run python tools/e2e_db.py
"""
import asyncio
import os
import subprocess
import sys

import asyncpg
from sqlalchemy.engine import make_url


async def main() -> None:
    url = make_url(os.environ["RS_DATABASE_URL"])
    admin = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    conn = await asyncpg.connect(admin)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


if __name__ == "__main__":
    asyncio.run(main())
