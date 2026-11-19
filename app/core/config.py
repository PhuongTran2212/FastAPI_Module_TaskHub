# app/core/config.py
from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, RedisDsn, SecretStr, model_validator
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

    celery_broker_url: RedisDsn = RedisDsn("redis://localhost:6379/1")
    job_connection_timeout_seconds: float = Field(default=2, gt=0, le=30)
    job_max_retries: int = Field(default=3, ge=0, le=10)
    assignment_email_enabled: bool = False
    assignment_email_expires_seconds: int = Field(default=3600, gt=0)
    smtp_host: str = Field(default="localhost", min_length=1)
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from_email: EmailStr = "taskhub@example.com"
    smtp_security: Literal["none", "starttls", "ssl"] = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_timeout_seconds: float = Field(default=5, gt=0, le=60)
    refresh_cleanup_interval_seconds: int = Field(default=300, ge=1)
    refresh_cleanup_batch_size: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_smtp_auth(self) -> "Settings":
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP username and password must be configured together")
        if self.smtp_username and self.smtp_security == "none":
            raise ValueError("SMTP authentication requires starttls or ssl")
        return self

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
