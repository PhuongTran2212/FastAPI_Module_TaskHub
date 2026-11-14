from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.enums import TaskPriority, TaskStatus
from app.models import Project, Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def list_filtered(
        self,
        *,
        page: int,
        limit: int,
        project_id: int,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> tuple[list[Task], int]:
        filters = [Task.project_id == project_id]

        for column, value in (
            (Task.status, status),
            (Task.priority, priority),
            (Task.assignee_id, assignee_id),
        ):
            if value is not None:
                filters.append(column == value)

        stmt = select(Task).where(*filters).order_by(Task.id)
        return await self.paginate(stmt, page=page, limit=limit)

    async def get_with_project(self, task_id: int) -> Task | None:
        # Nạp kèm project để biết workspace và trạng thái archive
        stmt = select(Task).options(joinedload(Task.project)).where(Task.id == task_id)
        return await self.session.scalar(stmt)

    async def unassign_in_workspace(self, workspace_id: int, user_id: int) -> None:
        project_ids = select(Project.id).where(Project.workspace_id == workspace_id)
        stmt = (
            update(Task)
            .where(Task.assignee_id == user_id, Task.project_id.in_(project_ids))
            .values(assignee_id=None)
        )
        await self.session.execute(stmt)
