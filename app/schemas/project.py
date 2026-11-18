from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, Field

from app.core.constants import MIN_TEXT_LENGTH, PROJECT_NAME_MAX_LENGTH
from app.core.enums import ProjectStatus
from app.schemas.base import BaseSchema, reject_null
from app.schemas.pagination import Page

ProjectName = Annotated[
    str,
    Field(min_length=MIN_TEXT_LENGTH, max_length=PROJECT_NAME_MAX_LENGTH),
]


class ProjectCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: str | None = None


class ProjectUpdate(BaseSchema):
    """PATCH: đổi tên/mô tả, archive (status=ARCHIVED) hoặc mở lại (ACTIVE)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[ProjectName | None, AfterValidator(reject_null)] = None
    description: str | None = None
    status: Annotated[ProjectStatus | None, AfterValidator(reject_null)] = None


class ProjectRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime


class ProjectPage(Page[ProjectRead]):
    pass
