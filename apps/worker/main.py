"""arq worker. Jobs are added phase by phase (docs/05). P1: the outbox relay, every second; email every 5 seconds
when RS_EMAIL_SENDER=worker.

Run: `uv run arq apps.worker.main.WorkerSettings`
"""
from arq import cron
from arq.connections import RedisSettings

from services.common.db import make_engine, make_sessionmaker
from services.common.outbox import relay_outbox
from services.common.settings import get_settings
from services.llm_gateway import build_gateway
from services.notifications import build_mailer, deliver_pending


async def startup(ctx: dict) -> None:
    ctx["engine"] = make_engine(get_settings().database_url)
    ctx["sessionmaker"] = make_sessionmaker(ctx["engine"])
    ctx["llm"] = build_gateway(get_settings(), sessionmaker=ctx["sessionmaker"])  # validates every prompt file
    ctx["mailer"] = build_mailer(get_settings())


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


async def send_email(ctx: dict) -> int:
    """email_outbox → SMTP, when RS_EMAIL_SENDER=worker (otherwise the API process sends)."""
    total = 0
    while sent := await deliver_pending(ctx["sessionmaker"], ctx["mailer"]):
        total += sent
    return total


class WorkerSettings:
    functions = [ping]
    cron_jobs = [cron(relay_events, second=set(range(60)), unique=True, run_at_startup=True)] + (
        [cron(send_email, second=set(range(0, 60, 5)), unique=True)] if get_settings().email_sender == "worker"
        else [])
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
