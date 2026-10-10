from functools import cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from RS_* environment variables (documented in .env.example)."""

    model_config = SettingsConfigDict(env_prefix="RS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://rs:rs@localhost:5432/rs"
    redis_url: str = "redis://localhost:6379/0"
    # Sign-in. Accounts are internal (users table; roles user | admin, managed by admins). People sign in with email
    # and password, and/or with Microsoft Entra ID SSO when RS_SSO=entra (only people an admin has added, matched by
    # email). RS_ENV=dev|test also offers a "sign in as" picker (POST /dev/token).
    sso: Literal["none", "entra"] = "none"
    password_sign_in: bool = True
    session_secret: str = ""  # HS256 key for the API's session tokens; required in prod (32+ characters)
    session_ttl_minutes: int = 480
    web_base_url: str = "http://localhost:5173"  # links in emails (invitations, approvals) point here
    auth_mode: str | None = None  # replaced by RS_SSO; set → a clear start-up error
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""  # the API's app registration: access tokens must be issued for it
    entra_spa_client_id: str = ""  # the web app's registration (public client, auth code + PKCE)
    entra_api_scope: str = ""  # default api://<api client id>/access_as_user
    entra_authority: str = "https://login.microsoftonline.com"
    public_base_url: str = "http://localhost:8000"
    # Object storage: Azure Blob Storage. Production uses managed identity (account URL); dev and CI use a connection
    # string (Azurite). "fs" keeps files on disk (tests, quick local runs).
    object_store: Literal["fs", "azure_blob"] = "fs"
    azure_storage_account_url: str = ""  # https://<account>.blob.core.windows.net (managed identity)
    azure_storage_connection_string: str = ""  # Azurite or a key-based account (dev only)
    azure_blob_container_exports: str = "exports"
    azure_blob_container_sources: str = "sources"
    # Email (invitations, password resets, approval requests): queued in email_outbox, sent over SMTP. Locally,
    # Mailpit (docker-compose) catches everything at http://localhost:8025. "console" logs instead of sending.
    email_backend: Literal["smtp", "console"] = "smtp"
    email_sender: Literal["api", "worker", "off"] = "api"  # which process sends queued email
    email_from: str = "Requirements Studio <no-reply@requirements-studio.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    llm_model: str = ""
    llm_mode: Literal["live", "record", "replay"] = "replay"
    llm_cassette_dir: str = ""  # default: tests/cassettes
    prompt_dir: str = ""  # default: prompts/
    ado_process: Literal["agile", "scrum"] = "agile"  # Azure Boards process: User Story vs Product Backlog Item
    default_tracker: Literal["jira", "ado"] = "jira"  # the tracker export ticked by default on the export screen
    export_dir: str = "var/exports"  # object_store=fs

    @property
    def dev_sign_in(self) -> bool:
        return self.env != "prod"

    @property
    def sso_enabled(self) -> bool:
        return self.sso == "entra"

    @property
    def session_key(self) -> str:
        return self.session_secret or "dev-only-session-secret-not-for-production"

    @property
    def api_scope(self) -> str:
        return self.entra_api_scope or f"api://{self.entra_api_client_id}/access_as_user"

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.auth_mode is not None:
            raise ValueError("RS_AUTH_MODE was replaced: accounts are internal now. Remove it; set RS_SSO=entra to "
                             "keep Microsoft sign-in")
        if self.sso == "entra":
            missing = [n for n in ("entra_tenant_id", "entra_api_client_id", "entra_spa_client_id")
                       if not getattr(self, n)]
            if missing:
                raise ValueError(f"RS_SSO=entra needs {', '.join('RS_' + m.upper() for m in missing)}")
        if not self.password_sign_in and self.sso == "none":
            raise ValueError("nobody could sign in: set RS_SSO=entra or RS_PASSWORD_SIGN_IN=true")
        if self.env == "prod" and len(self.session_secret) < 32:
            raise ValueError("RS_SESSION_SECRET (32+ random characters) is required in prod")
        if self.object_store == "azure_blob" and not (self.azure_storage_account_url
                                                       or self.azure_storage_connection_string):
            raise ValueError("RS_OBJECT_STORE=azure_blob needs RS_AZURE_STORAGE_ACCOUNT_URL (managed identity) or "
                             "RS_AZURE_STORAGE_CONNECTION_STRING (Azurite)")
        if self.env == "prod" and self.azure_storage_connection_string:
            raise ValueError("use managed identity (RS_AZURE_STORAGE_ACCOUNT_URL) in prod, not a connection string")
        return self


@cache
def get_settings() -> Settings:
    return Settings()
