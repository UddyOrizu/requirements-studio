"""FastAPI app. P0: health, identity and the dev OIDC stub. Module routers are added phase by phase (docs/05)."""
from dataclasses import asdict

from fastapi import APIRouter, FastAPI

from services.common.settings import Settings, get_settings
from services.identity_audit.auth import JwksVerifier
from services.identity_audit.dev_oidc import DevOidc

from .deps import CurrentUser

API_PREFIX = "/api/v1"
DEV_OIDC_PREFIX = "/dev/oidc"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Requirements Studio", version="0.1.0")
    app.state.settings = settings

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

    app.include_router(api)
    return app


def app() -> FastAPI:
    """uvicorn factory: `uvicorn apps.api.main:app --factory`."""
    return create_app()
