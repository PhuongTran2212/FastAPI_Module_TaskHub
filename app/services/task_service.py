from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError

from app.core.enums import TaskPriority, TaskStatus
from app.core.exceptions import (
    ConflictException,
    InvalidReferenceException,
    NotFoundException,
)
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate


class TaskService:
    def __init__(
        self,
        repo: TaskRepository,
        projects: ProjectRepository,
        users: UserRepository,
    ) -> None:
        self.repo = repo
        self.projects = projects
        self.users = users

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        try:
            async with self.repo.session.begin():
                yield
        except IntegrityError as exc:
            raise ConflictException() from exc

    async def list_tasks(
        self,
        page: int,
        limit: int,
        project_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> TaskPage:
        items, total = await self.repo.list_filtered(
            page=page,
            limit=limit,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
        )

        return TaskPage(
            items=[TaskRead.model_validate(item) for item in items],
            total=total,
            page=page,
            limit=limit,
        )

    async def get_task(self, task_id: int) -> TaskRead:
        task = await self.repo.get(task_id)

        if task is None:
            raise NotFoundException("Task")

        return TaskRead.model_validate(task)

    async def create_task(self, data: TaskCreate) -> TaskRead:
        async with self._transaction():
            project = await self.projects.get(data.project_id)
            if project is None:
                raise InvalidReferenceException("Project")

            creator = await self.users.get(data.created_by)
            if creator is None:
                raise InvalidReferenceException("Creator")

            if data.assignee_id is not None:
                assignee = await self.users.get(data.assignee_id)
                if assignee is None:
                    raise InvalidReferenceException("Assignee")

            values = data.model_dump()
            values["status"] = TaskStatus.TODO

            task = await self.repo.create(values)
            return TaskRead.model_validate(task)

    async def update_task(
        self,
        task_id: int,
        data: TaskUpdate,
    ) -> TaskRead:
        async with self._transaction():
            task = await self.repo.get(task_id)

            if task is None:
                raise NotFoundException("Task")

            changes = data.model_dump(exclude_unset=True)

            assignee_id = changes.get("assignee_id")
            if assignee_id is not None:
                assignee = await self.users.get(assignee_id)
                if assignee is None:
                    raise InvalidReferenceException("Assignee")

            task = await self.repo.update(task, changes)
            return TaskRead.model_validate(task)

    async def delete_task(self, task_id: int) -> None:
        async with self._transaction():
            task = await self.repo.get(task_id)

            if task is None:
                raise NotFoundException("Task")

            await self.repo.delete(task)