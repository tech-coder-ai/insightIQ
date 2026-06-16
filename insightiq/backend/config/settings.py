from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class JwtSettings(BaseModel):
    issuer: str = "insightiq"
    audience: str = "insightiq"
    access_token_ttl_seconds: int = 60 * 60

    # Phase 1: keep simple. Phase 6 hardening should move key management into Vault / KMS rotation.
    private_key_pem: str = Field(default="", repr=False)
    public_key_pem: str = ""


class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://insightiq:insightiq@localhost:5432/insightiq"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INSIGHTIQ_", env_nested_delimiter="__")

    env: str = "dev"
    database: DatabaseSettings = DatabaseSettings()
    jwt: JwtSettings = JwtSettings()


class SettingsSnapshot(BaseModel):
    env: str
    database_url: str
    jwt_issuer: str
    jwt_audience: str
    jwt_access_token_ttl_seconds: int

    @classmethod
    def from_settings(cls, s: AppSettings) -> "SettingsSnapshot":
        return cls(
            env=s.env,
            database_url=s.database.url,
            jwt_issuer=s.jwt.issuer,
            jwt_audience=s.jwt.audience,
            jwt_access_token_ttl_seconds=s.jwt.access_token_ttl_seconds,
        )


class SettingsResolver:
    """
    Phase 1: env-only settings.
    Later phases will merge env → YAML defaults → tenant overrides → collection overrides → request-time overrides.
    """

    def resolve(self, request_overrides: dict[str, Any] | None = None) -> AppSettings:
        settings = AppSettings()
        if request_overrides:
            # Minimal override support for Phase 1; keep shape stable for later layering.
            settings = settings.model_copy(update=request_overrides)
        return settings


@lru_cache(maxsize=1)
def get_settings_resolver() -> SettingsResolver:
    return SettingsResolver()

