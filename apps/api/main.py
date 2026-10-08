"""FastAPI app. Module routers are added phase by phase (docs/05): P1 adds M3 (processes, patches, fork)."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import APIRouter, FastAPI

from services.common.db import make_engine, make_sessionmaker, utcnow
from services.common.settings import Settings, get_settings
from services.ideas.api import dev_router
from services.ideas.api import router as ideas_router
from services.identity_audit.auth import JwksVerifier
from services.identity_audit.dev_oidc import DevOidc
from services.improve.api import router as improve_router
from services.intake.api import router as intake_router
from services.ir_store.api import router as ir_store_router
from services.llm_gateway import build_gateway

from . import problems
from .deps import CurrentUser

API_PREFIX = "/api/v1"
DEV_OIDC_PREFIX = "/dev/oidc"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)  # connects lazily

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="Requirements Studio", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.clock = utcnow
    app.state.llm = build_gateway(settings, sessionmaker=app.state.sessionmaker)  # validates every prompt file
    problems.register(app)

    if settings.use_dev_oidc:
        dev = DevOidc(issuer=settings.public_base_url.rstrip("/") + DEV_OIDC_PREFIX, audience=settings.oidc_audience)
        app.include_router(dev.router(), prefix=DEV_OIDC_PREFIX)
        app.state.verifier = dev.verifier()
        app.state.dev_oidc = dev
    else:
        app.state.verifier = JwksVerifier(settings.oidc_issuer, settings.oidc_audience)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok"}

    api = APIRouter(prefix=API_PREFIX)

    @api.get("/me", tags=["identity"])
    def me(user: CurrentUser) -> dict:
        return asdict(user)

    api.include_router(ir_store_router)
    api.include_router(intake_router)
    api.include_router(improve_router)
    api.include_router(ideas_router)
    app.include_router(api)
    if settings.env != "prod":
        app.include_router(dev_router)  # POST /dev/seed: reset to a sample scenario (demo and UI tests)
    return app


def app() -> FastAPI:
    """uvicorn factory: `uvicorn apps.api.main:app --factory`."""
    return create_app()
