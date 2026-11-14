from typing import Generic, TypeVar

from pydantic import Field

from app.core.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_NUMBER,
    MAX_PAGE_LIMIT,
    MIN_PAGE_LIMIT,
    MIN_PAGE_NUMBER,
)
from app.schemas.base import BaseSchema

ItemT = TypeVar("ItemT")


class PaginationParams(BaseSchema):
    page: int = Field(default=DEFAULT_PAGE_NUMBER, ge=MIN_PAGE_NUMBER)
    limit: int = Field(
        default=DEFAULT_PAGE_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_PAGE_LIMIT,
    )


class Page(BaseSchema, Generic[ItemT]):
    """Kết quả phân trang dùng chung: class con đặt tên schema cho OpenAPI."""

    items: list[ItemT]
    total: int
    page: int
    limit: int
