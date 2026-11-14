from typing import Annotated

from pydantic import AfterValidator, ConfigDict, Field

from app.core.constants import (
    DEFAULT_LABEL_COLOR,
    LABEL_COLOR_PATTERN,
    LABEL_NAME_MAX_LENGTH,
    MIN_TEXT_LENGTH,
)
from app.schemas.base import BaseSchema, reject_null


def normalize_color(value: str) -> str:
    return value.upper()


LabelName = Annotated[
    str,
    Field(min_length=MIN_TEXT_LENGTH, max_length=LABEL_NAME_MAX_LENGTH),
]
# Mã màu hex #RRGGBB, lưu chữ hoa để "#ff0000" và "#FF0000" là một
LabelColor = Annotated[
    str,
    Field(pattern=LABEL_COLOR_PATTERN, examples=[DEFAULT_LABEL_COLOR]),
    AfterValidator(normalize_color),
]


class LabelCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    name: LabelName
    color: LabelColor = DEFAULT_LABEL_COLOR


class LabelUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[LabelName | None, AfterValidator(reject_null)] = None
    color: Annotated[LabelColor | None, AfterValidator(reject_null)] = None


class LabelRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    color: str
