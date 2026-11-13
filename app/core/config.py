from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    DEFAULT_ACCESS_TOKEN_MINUTES,
    DEFAULT_REFRESH_TOKEN_DAYS,
    JWT_SECRET_MIN_LENGTH,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    jwt_secret_key: str = Field(min_length=JWT_SECRET_MIN_LENGTH)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=DEFAULT_ACCESS_TOKEN_MINUTES, gt=0)
    refresh_token_expire_days: int = Field(default=DEFAULT_REFRESH_TOKEN_DAYS, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
