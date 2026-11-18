from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Label, task_labels
from app.repositories.base import BaseRepository


class LabelRepository(BaseRepository[Label]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Label)

    async def get_with_project(self, label_id: int) -> Label | None:
        stmt = (
            select(Label).options(joinedload(Label.project)).where(Label.id == label_id)
        )
        return await self.session.scalar(stmt)

    async def list_by_project(self, project_id: int) -> list[Label]:
        stmt = (
            select(Label)
            .where(Label.project_id == project_id)
            .order_by(Label.name, Label.id)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def list_for_task(self, task_id: int) -> list[Label]:
        stmt = (
            select(Label)
            .join(task_labels, task_labels.c.label_id == Label.id)
            .where(task_labels.c.task_id == task_id)
            .order_by(Label.name, Label.id)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def attach(self, task_id: int, label_id: int) -> None:
        # Gán lại label đã gán không lỗi, kể cả khi 2 request chạy song song
        stmt = (
            insert(task_labels)
            .values(task_id=task_id, label_id=label_id)
            .on_conflict_do_nothing()
        )
        await self.session.execute(stmt)

    async def detach(self, task_id: int, label_id: int) -> None:
        stmt = delete(task_labels).where(
            task_labels.c.task_id == task_id,
            task_labels.c.label_id == label_id,
        )
        await self.session.execute(stmt)
