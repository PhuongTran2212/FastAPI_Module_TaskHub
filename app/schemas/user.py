from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from app.core import messages
from app.core.constants import (
    BCRYPT_MAX_BYTES,
    EMAIL_MAX_LENGTH,
    MIN_TEXT_LENGTH,
    PASSWORD_MIN_LENGTH,
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
    EmailStr, Field(max_length=EMAIL_MAX_LENGTH), AfterValidator(normalize_email)
]
Password = Annotated[
    str,
    StringConstraints(
        strip_whitespace=False,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=BCRYPT_MAX_BYTES,
    ),
    AfterValidator(check_password_bytes),
]
CurrentPassword = Annotated[
    str,
    StringConstraints(
        strip_whitespace=False, min_length=MIN_TEXT_LENGTH, max_length=BCRYPT_MAX_BYTES
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
