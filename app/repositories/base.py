from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_PAGE_LIMIT
from app.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def get(self, item_id: int) -> T | None:
        return await self.session.get(self.model, item_id)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[T]:
        stmt = (
            select(self.model)
            .order_by(*self.model.__table__.primary_key.columns)
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count(self, *filters: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(self.model).where(*filters)
        return (await self.session.scalar(stmt)) or 0

    async def paginate(
        self,
        stmt: Select[tuple[T]],
        *,
        page: int,
        limit: int,
    ) -> tuple[list[T], int]:
        """Trả về (items của trang, tổng số dòng khớp điều kiện của stmt)."""
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = (await self.session.scalar(count_stmt)) or 0

        result = await self.session.scalars(
            stmt.offset((page - 1) * limit).limit(limit)
        )
        return list(result.all()), total

    async def list_page(self, *, page: int, limit: int) -> tuple[list[T], int]:
        stmt = select(self.model).order_by(*self.model.__table__.primary_key.columns)
        return await self.paginate(stmt, page=page, limit=limit)

    async def create(self, values: dict[str, Any]) -> T:
        item = self.model(**values)
        self.session.add(item)

        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update(self, item: T, values: dict[str, Any]) -> T:
        for field, value in values.items():
            setattr(item, field, value)

        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: T) -> None:
        await self.session.delete(item)
        await self.session.flush()
