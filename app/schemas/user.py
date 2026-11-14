# app/schemas/user.py
from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.core import messages
from app.core.constants import (
    BCRYPT_MAX_BYTES,
    EMAIL_MAX_LENGTH,
    MIN_TEXT_LENGTH,
    PASSWORD_MIN_LENGTH,
    USER_FULL_NAME_MAX_LENGTH,
)
from app.core.enums import UserRole
from app.schemas.base import BaseSchema


def normalize_email(value: str) -> str:
    return value.strip().lower()


def check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(messages.PASSWORD_TOO_LONG.format(limit=BCRYPT_MAX_BYTES))
    return value


Email = Annotated[
    EmailStr,
    Field(max_length=EMAIL_MAX_LENGTH),
    AfterValidator(normalize_email),
]

# BaseSchema strip khoảng trắng mọi chuỗi; riêng mật khẩu phải giữ nguyên từng ký tự
Password = Annotated[
    str,
    StringConstraints(
        strip_whitespace=False,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=BCRYPT_MAX_BYTES,
    ),
    AfterValidator(check_password_bytes),
]

# Mật khẩu đang dùng (login, đổi mật khẩu): không áp độ dài tối thiểu mới,
# nhưng vẫn giới hạn để không nhận body lớn tuỳ ý
CurrentPassword = Annotated[
    str,
    StringConstraints(
        strip_whitespace=False,
        min_length=MIN_TEXT_LENGTH,
        max_length=BCRYPT_MAX_BYTES,
    ),
    AfterValidator(check_password_bytes),
]


class UserRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(
        default=None,
        min_length=MIN_TEXT_LENGTH,
        max_length=USER_FULL_NAME_MAX_LENGTH,
    )

    @model_validator(mode="after")
    def reject_null_full_name(self) -> "UserUpdate":
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError(messages.FULL_NAME_CANNOT_BE_NULL)
        return self


class ChangePasswordRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    current_password: CurrentPassword
    new_password: Password

    @model_validator(mode="after")
    def new_password_must_differ(self) -> "ChangePasswordRequest":
        if self.new_password == self.current_password:
            raise ValueError(messages.PASSWORD_MUST_DIFFER)
        return self
