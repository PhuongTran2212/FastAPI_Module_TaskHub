from typing import Any, Generic, TypeVar

from sqlalchemy import select
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
