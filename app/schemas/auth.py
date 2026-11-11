# app/schemas/auth.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import Email, Password


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    full_name: str = Field(min_length=1, max_length=255)
    password: Password


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
