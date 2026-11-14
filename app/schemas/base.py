from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from app.core import messages

ValueT = TypeVar("ValueT")


class BaseSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


def reject_null(value: ValueT | None) -> ValueT:
    """Dùng với AfterValidator cho field PATCH: được bỏ trống nhưng không được null."""
    if value is None:
        raise ValueError(messages.FIELD_CANNOT_BE_NULL)
    return value
