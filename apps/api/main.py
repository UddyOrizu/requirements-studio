"""FastAPI app. Module routers are added phase by phase (docs/05): P1 adds M3 (processes, patches, fork)."""
import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from services.approvals.api import router as approvals_router
from services.common.db import make_engine, make_sessionmaker, utcnow
from services.common.settings import Settings, get_settings
from services.export.api import router as export_router
from services.export.store import build_store
from services.ideas.api import dev_router
from services.ideas.api import router as ideas_router
from services.identity_audit import dev as dev_auth
from services.identity_audit.api import auth_router
from services.identity_audit.api import router as identity_router
from services.identity_audit.auth import EntraVerifier
from services.identity_audit.sessions import SessionTokens
from services.improve.api import router as improve_router
from services.intake.api import router as intake_router
from services.ir_store.api import router as ir_store_router
from services.llm_gateway import build_gateway
from services.notifications import build_mailer, deliver_pending

from . import problems

API_PREFIX = "/api/v1"
EMAIL_POLL_SECONDS = 5
log = logging.getLogger(__name__)


async def _send_email_forever(app: FastAPI) -> None:
    """RS_EMAIL_SENDER=api: send queued email from this process (SKIP LOCKED, so several replicas are safe)."""
    while True:
        try:
            await deliver_pending(app.state.sessionmaker, app.state.mailer)
        except Exception:  # noqa: BLE001 (keep sending; the next round retries)
            log.exception("email delivery round failed")
        await asyncio.sleep(EMAIL_POLL_SECONDS)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)  # connects lazily

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sender = asyncio.create_task(_send_email_forever(app)) if settings.email_sender == "api" else None
        yield
        if sender is not None:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
        await engine.dispose()
        if hasattr(app.state.export_store, "close"):
            await app.state.export_store.close()

    app = FastAPI(title="Requirements Studio", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.clock = utcnow
    app.state.export_store = build_store(settings)
    app.state.llm = build_gateway(settings, sessionmaker=app.state.sessionmaker)  # validates every prompt file
    app.state.mailer = build_mailer(settings)
    app.state.session_tokens = SessionTokens(settings.session_key, settings.session_ttl_minutes)
    app.state.entra = EntraVerifier(
        tenant_id=settings.entra_tenant_id, api_client_id=settings.entra_api_client_id,
        api_scope=settings.api_scope, authority=settings.entra_authority) if settings.sso_enabled else None
    problems.register(app)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok"}

    app.include_router(auth_router)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(identity_router)
    api.include_router(approvals_router)
    api.include_router(ir_store_router)
    api.include_router(intake_router)
    api.include_router(improve_router)
    api.include_router(ideas_router)
    api.include_router(export_router)
    app.include_router(api)
    if settings.dev_sign_in:
        app.include_router(dev_auth.router())  # /dev/token, /dev/users, /dev/emails
        app.include_router(dev_router)  # POST /dev/seed: reset to a sample scenario (demo and UI tests)
    return app


def app() -> FastAPI:
    """uvicorn factory: `uvicorn apps.api.main:app --factory`."""
    return create_app()
