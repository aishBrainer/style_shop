"""Settings normalisation.

Covers the deployment footgun: managed Postgres hosts hand out connection
strings with no SQLAlchemy driver, which the async engine cannot use.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


class TestDatabaseUrlNormalisation:
    @pytest.mark.parametrize(
        ("supplied", "expected"),
        [
            # Render / Railway / Fly hand out this shape.
            (
                "postgresql://u:p@host.internal:5432/db",
                "postgresql+asyncpg://u:p@host.internal:5432/db",
            ),
            # Heroku's legacy prefix, still emitted by several providers.
            (
                "postgres://u:p@host.internal:5432/db",
                "postgresql+asyncpg://u:p@host.internal:5432/db",
            ),
            # Already correct — must pass through untouched.
            (
                "postgresql+asyncpg://u:p@host:5432/db",
                "postgresql+asyncpg://u:p@host:5432/db",
            ),
        ],
    )
    def test_coerces_bare_urls_to_asyncpg(self, supplied: str, expected: str) -> None:
        assert Settings(database_url=supplied).database_url == expected

    def test_only_rewrites_the_scheme(self) -> None:
        """A password containing 'postgresql://' must not be mangled — replace
        is bounded to the first occurrence for exactly this reason."""
        url = "postgresql://user:postgresql://weird@host:5432/db"
        result = Settings(database_url=url).database_url
        assert result.startswith("postgresql+asyncpg://")
        assert result.count("postgresql+asyncpg://") == 1

    def test_sync_url_derives_psycopg2(self) -> None:
        """Celery workers need a blocking driver off the same variable."""
        settings = Settings(database_url="postgresql://u:p@host:5432/db")
        assert settings.sync_database_url == "postgresql+psycopg2://u:p@host:5432/db"

    def test_sync_url_works_when_driver_already_present(self) -> None:
        settings = Settings(database_url="postgresql+asyncpg://u:p@host:5432/db")
        assert settings.sync_database_url == "postgresql+psycopg2://u:p@host:5432/db"


class TestSecretKeyGuard:
    def test_rejects_the_placeholder_in_production(self) -> None:
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings(environment="production", secret_key="change-me-dev-only")

    def test_allows_the_placeholder_in_development(self) -> None:
        assert Settings(environment="development", secret_key="change-me-dev-only")


class TestDerivedValues:
    def test_cors_origins_split_and_trimmed(self) -> None:
        settings = Settings(cors_origins="http://a.test, https://b.test ,")
        assert settings.cors_origin_list == ["http://a.test", "https://b.test"]

    def test_upload_limit_in_bytes(self) -> None:
        assert Settings(max_upload_mb=20).max_upload_bytes == 20 * 1024 * 1024
