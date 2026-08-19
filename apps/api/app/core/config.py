"""Application settings.

Single source of truth for configuration. Nothing in the codebase should read
`os.environ` directly — import `settings` from here instead (§101: no critical
configuration living only on a developer's laptop).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- general ---
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    app_name: str = "AI Fashion Studio"
    api_v1_prefix: str = "/api/v1"

    # --- security ---
    secret_key: str = "change-me-dev-only-do-not-use-in-production"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    cookie_domain: str = ""
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"

    # --- database ---
    database_url: str = "postgresql+asyncpg://fashion:fashion@localhost:5432/fashion_studio"

    # --- redis / queue ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- storage ---
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "fashion-studio"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True
    signed_url_ttl_seconds: int = 900

    # --- oauth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # --- email ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@aifashionstudio.local"

    # --- uploads ---
    max_upload_mb: int = 20
    allowed_image_mimes: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )

    # --- ai ---
    vton_provider: str = "mock"
    image_provider: str = "mock"
    segmentation_provider: str = "rembg"
    upscale_provider: str = "mock"
    video_provider: str = "mock"
    ai_device: Literal["auto", "cuda", "cpu", "mps"] = "auto"
    ai_weights_dir: str = "/weights"
    max_concurrent_jobs_per_worker: int = 1
    job_timeout_seconds: int = 900
    job_max_retries: int = 2
    allow_non_commercial_models: bool = False

    # --- frontend ---
    web_url: str = "http://localhost:3000"

    # --- rate limits (requests per window, seconds) ---
    rate_limit_auth: tuple[int, int] = (10, 60)
    rate_limit_upload: tuple[int, int] = (60, 60)
    rate_limit_generate: tuple[int, int] = (30, 60)

    @field_validator("secret_key")
    @classmethod
    def _reject_default_secret_in_prod(cls, v: str, info) -> str:
        env = (info.data or {}).get("environment")
        if env == "production" and "change-me" in v:
            raise ValueError("SECRET_KEY must be set to a real value in production")
        return v

    @field_validator("database_url")
    @classmethod
    def _normalise_database_driver(cls, v: str) -> str:
        """Force the asyncpg driver onto a bare Postgres URL.

        Managed hosts (Render, Heroku, Railway, Fly) hand out connection
        strings as `postgres://` or `postgresql://` with no driver. SQLAlchemy
        would pick psycopg2 for those, which the async engine cannot use — the
        app dies at start-up with a confusing InvalidRequestError. Coerce here
        so the platform's own DATABASE_URL works unedited.
        """
        if v.startswith("postgres://"):  # legacy Heroku-style prefix
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Celery workers use blocking SQLAlchemy sessions."""
        return self.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql+psycopg2://"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
