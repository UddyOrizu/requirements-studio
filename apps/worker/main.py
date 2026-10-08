"""arq worker. P0 registers only a health job; module jobs are added phase by phase (docs/05).

Run: `uv run arq apps.worker.main.WorkerSettings`
"""
from arq.connections import RedisSettings

from services.common.settings import get_settings


async def ping(ctx: dict) -> str:
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
