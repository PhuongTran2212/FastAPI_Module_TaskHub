from datetime import date, datetime

from pydantic import ConfigDict, Field, field_validator

from app.core.constants import TASK_TITLE_MAX_LENGTH
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.base import BaseSchema


def validate_due_date(value: date | None) -> date | None:
    if value is not None and value < date.today():
        raise ValueError("due_date cannot be in the past")

    return value


class TaskBase(BaseSchema):
    title: str = Field(
        min_length=1,
        max_length=TASK_TITLE_MAX_LENGTH,
    )
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_id: int | None = Field(default=None, gt=0)


class TaskCreate(TaskBase):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    created_by: int = Field(gt=0)

    @field_validator("due_date")
    @classmethod
    def check_due_date(cls, value: date | None) -> date | None:
        return validate_due_date(value)


class TaskUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=TASK_TITLE_MAX_LENGTH,
    )
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "status", "priority")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")

        return value

    @field_validator("due_date")
    @classmethod
    def check_due_date(cls, value: date | None) -> date | None:
        return validate_due_date(value)


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    status: TaskStatus
    created_at: datetime


class TaskPage(BaseSchema):
    items: list[TaskRead]
    total: int
    page: int
    limit: int