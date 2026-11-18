# app/core/config.py
from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    DEFAULT_ACCESS_TOKEN_MINUTES,
    DEFAULT_REFRESH_TOKEN_DAYS,
    JWT_SECRET_MIN_LENGTH,
    REDIS_TIMEOUT_SECONDS,
    TASK_CACHE_MAX_TTL_SECONDS,
    TASK_CACHE_TTL_SECONDS,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str

    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    task_cache_enabled: bool = True
    task_cache_ttl_seconds: int = Field(
        default=TASK_CACHE_TTL_SECONDS,
        gt=0,
        le=TASK_CACHE_MAX_TTL_SECONDS,
    )
    redis_timeout_seconds: float = Field(default=REDIS_TIMEOUT_SECONDS, gt=0, le=5)

    jwt_secret_key: str = Field(min_length=JWT_SECRET_MIN_LENGTH)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(
        default=DEFAULT_ACCESS_TOKEN_MINUTES,
        gt=0,
    )
    refresh_token_expire_days: int = Field(
        default=DEFAULT_REFRESH_TOKEN_DAYS,
        gt=0,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
