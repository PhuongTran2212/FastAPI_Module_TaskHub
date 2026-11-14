from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TaskPriority, TaskStatus
from app.models import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def list_filtered(
        self,
        *,
        page: int,
        limit: int,
        project_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> tuple[list[Task], int]:
        filters = []

        for column, value in (
            (Task.project_id, project_id),
            (Task.status, status),
            (Task.priority, priority),
            (Task.assignee_id, assignee_id),
        ):
            if value is not None:
                filters.append(column == value)

        stmt = (
            select(Task)
            .where(*filters)
            .order_by(Task.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )

        result = await self.session.scalars(stmt)
        items = list(result.all())

        count_stmt = select(func.count()).select_from(Task).where(*filters)

        total = (await self.session.scalar(count_stmt)) or 0

        return items, total
