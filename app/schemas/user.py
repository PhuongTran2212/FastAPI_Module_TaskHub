# app/schemas/user.py
from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)

from app.core.enums import UserRole

BCRYPT_MAX_BYTES = 72


def normalize_email(value: str) -> str:
    return value.strip().lower()


def check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes in UTF-8")
    return value


Email = Annotated[EmailStr, AfterValidator(normalize_email)]
Password = Annotated[
    str,
    Field(min_length=8, max_length=72),
    AfterValidator(check_password_bytes),
]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def reject_null_full_name(self) -> "UserUpdate":
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: Password

    @model_validator(mode="after")
    def new_password_must_differ(self) -> "ChangePasswordRequest":
        if self.new_password == self.current_password:
            raise ValueError("New password must differ from current password")
        return self
