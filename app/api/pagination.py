from typing import Annotated

from fastapi import Depends, Query

from app.core.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_NUMBER,
    MAX_PAGE_LIMIT,
    MIN_PAGE_LIMIT,
    MIN_PAGE_NUMBER,
)
from app.schemas.pagination import PaginationParams


def get_pagination(
    page: Annotated[int, Query(ge=MIN_PAGE_NUMBER)] = DEFAULT_PAGE_NUMBER,
    limit: Annotated[
        int, Query(ge=MIN_PAGE_LIMIT, le=MAX_PAGE_LIMIT)
    ] = DEFAULT_PAGE_LIMIT,
) -> PaginationParams:
    return PaginationParams(page=page, limit=limit)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination)]
