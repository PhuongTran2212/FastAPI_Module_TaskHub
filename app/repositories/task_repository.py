from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.enums import TaskPriority, TaskStatus
from app.models import Project, Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def _invalidate_task_list(self, project_id: int) -> None:
        # This UPDATE is committed or rolled back together with the task change.
        await self.session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(task_cache_version=Project.task_cache_version + 1)
        )

    async def create(self, values: dict[str, Any]) -> Task:
        task = await super().create(values)
        await self._invalidate_task_list(task.project_id)
        return task

    async def update(self, item: Task, values: dict[str, Any]) -> Task:
        task = await super().update(item, values)
        await self._invalidate_task_list(task.project_id)
        return task

    async def delete(self, item: Task) -> None:
        project_id = item.project_id
        await super().delete(item)
        await self._invalidate_task_list(project_id)

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
            .returning(Task.project_id)
        )
        project_ids_changed = set((await self.session.scalars(stmt)).all())
        for project_id in sorted(project_ids_changed):
            await self._invalidate_task_list(project_id)
