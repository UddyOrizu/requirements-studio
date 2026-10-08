"""arq worker. Jobs are added phase by phase (docs/05). P1: the outbox relay, every second.

Run: `uv run arq apps.worker.main.WorkerSettings`
"""
from arq import cron
from arq.connections import RedisSettings

from services.common.db import make_engine, make_sessionmaker
from services.common.outbox import relay_outbox
from services.common.settings import get_settings
from services.llm_gateway import build_gateway


async def startup(ctx: dict) -> None:
    ctx["engine"] = make_engine(get_settings().database_url)
    ctx["sessionmaker"] = make_sessionmaker(ctx["engine"])
    ctx["llm"] = build_gateway(get_settings(), sessionmaker=ctx["sessionmaker"])  # validates every prompt file


async def shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


async def ping(ctx: dict) -> str:
    return "pong"


async def relay_events(ctx: dict) -> int:
    """Outbox → Redis Stream `rs:events` (docs/06: transactional outbox, at-least-once)."""
    total = 0
    while published := await relay_outbox(ctx["sessionmaker"], ctx["redis"]):
        total += published
    return total


class WorkerSettings:
    functions = [ping]
    cron_jobs = [cron(relay_events, second=set(range(60)), unique=True, run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
