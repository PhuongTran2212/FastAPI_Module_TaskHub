from datetime import datetime

from pydantic import ConfigDict, Field

from app.core.constants import COMMENT_CONTENT_MAX_LENGTH, MIN_TEXT_LENGTH
from app.schemas.base import BaseSchema
from app.schemas.pagination import Page


class CommentCreate(BaseSchema):
    # task_id lấy từ path, author_id lấy từ token
    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=COMMENT_CONTENT_MAX_LENGTH,
    )


class CommentRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    author_id: int
    content: str
    created_at: datetime


class CommentPage(Page[CommentRead]):
    pass
