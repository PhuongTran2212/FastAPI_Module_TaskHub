# app/schemas/auth.py
from typing import Literal

from pydantic import ConfigDict, Field

from app.core.constants import (
    MIN_TEXT_LENGTH,
    TOKEN_MAX_LENGTH,
    USER_FULL_NAME_MAX_LENGTH,
)
from app.schemas.base import BaseSchema
from app.schemas.user import CurrentPassword, Email, Password


class RegisterRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    email: Email
    full_name: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=USER_FULL_NAME_MAX_LENGTH,
    )
    password: Password


class LoginRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: CurrentPassword


class RefreshTokenRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=TOKEN_MAX_LENGTH,
    )


class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
