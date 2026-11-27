from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, Field

from app.core import messages
from app.core.constants import MIN_TEXT_LENGTH, TASK_TITLE_MAX_LENGTH
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.base import BaseSchema, reject_null
from app.schemas.pagination import Page


def validate_due_date(value: date | None) -> date | None:
    if value is not None and value < date.today():
        raise ValueError(messages.DUE_DATE_IN_PAST)

    return value


TaskDueDate = Annotated[date | None, AfterValidator(validate_due_date)]


class TaskBase(BaseSchema):
    title: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=TASK_TITLE_MAX_LENGTH,
    )
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_id: int | None = Field(default=None, gt=0)


class TaskCreate(TaskBase):
    # project_id lấy từ path /projects/{project_id}/tasks
    model_config = ConfigDict(extra="forbid")

    due_date: TaskDueDate = None


class TaskUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, AfterValidator(reject_null)] = Field(
        default=None,
        min_length=MIN_TEXT_LENGTH,
        max_length=TASK_TITLE_MAX_LENGTH,
    )
    description: str | None = None
    status: Annotated[TaskStatus | None, AfterValidator(reject_null)] = None
    priority: Annotated[TaskPriority | None, AfterValidator(reject_null)] = None
    due_date: TaskDueDate = None
    assignee_id: int | None = Field(default=None, gt=0)


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    status: TaskStatus
    created_at: datetime


class TaskPage(Page[TaskRead]):
    pass
