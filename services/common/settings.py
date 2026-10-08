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
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_sources: str = "rs-sources"
    s3_bucket_exports: str = "rs-exports"
    oidc_issuer: str = ""
    oidc_audience: str = "requirements-studio"
    public_base_url: str = "http://localhost:8000"
    llm_model: str = ""

    @property
    def use_dev_oidc(self) -> bool:
        return self.env == "dev" and not self.oidc_issuer

    @model_validator(mode="after")
    def _prod_needs_real_idp(self) -> Self:
        if self.env != "dev" and not self.oidc_issuer:
            raise ValueError("RS_OIDC_ISSUER is required outside dev (the dev OIDC stub only runs with RS_ENV=dev)")
        return self


@cache
def get_settings() -> Settings:
    return Settings()
