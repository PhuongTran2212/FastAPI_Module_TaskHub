from __future__ import annotations

import builtins
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
        stmt = self._ordered_select().offset(offset).limit(limit)

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
    ) -> tuple[builtins.list[T], int]:
        """Trả về (items của trang, tổng số dòng khớp điều kiện của stmt)."""
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = (await self.session.scalar(count_stmt)) or 0

        result = await self.session.scalars(
            stmt.offset((page - 1) * limit).limit(limit)
        )
        return list(result.all()), total

    def _ordered_select(self) -> Select[tuple[T]]:
        return select(self.model).order_by(*self.model.__mapper__.primary_key)

    async def list_page(self, *, page: int, limit: int) -> tuple[builtins.list[T], int]:
        return await self.paginate(self._ordered_select(), page=page, limit=limit)

    async def create(self, values: dict[str, Any]) -> T:
        item = self.model(**values)
        self.session.add(item)

        await self.session.flush()
        # PostgreSQL INSERT RETURNING already populates IDs/server defaults.
        return item

    async def update(self, item: T, values: dict[str, Any]) -> T:
        for field, value in values.items():
            setattr(item, field, value)

        await self.session.flush()
        # Base eagerly fetches defaults before async response serialization.
        return item

    async def delete(self, item: T) -> None:
        await self.session.delete(item)
        await self.session.flush()
