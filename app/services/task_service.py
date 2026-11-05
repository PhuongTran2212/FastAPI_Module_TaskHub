from app.core.enums import TaskPriority, TaskStatus
from app.models import Project, User
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate


class InvalidTaskReference(ValueError):
    pass


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo

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

    async def get_task(self, task_id: int) -> TaskRead | None:
        task = await self.repo.get(task_id)

        if task is None:
            return None

        return TaskRead.model_validate(task)

    async def create_task(self, data: TaskCreate) -> TaskRead:
        async with self.repo.session.begin():
            project = await self.repo.session.get(Project, data.project_id)
            if project is None:
                raise InvalidTaskReference("Project not found")

            creator = await self.repo.session.get(User, data.created_by)
            if creator is None:
                raise InvalidTaskReference("Creator not found")

            if data.assignee_id is not None:
                assignee = await self.repo.session.get(User, data.assignee_id)
                if assignee is None:
                    raise InvalidTaskReference("Assignee not found")

            task = await self.repo.create(data.model_dump())
            return TaskRead.model_validate(task)

    async def update_task(
        self,
        task_id: int,
        data: TaskUpdate,
    ) -> TaskRead | None:
        async with self.repo.session.begin():
            task = await self.repo.get(task_id)
            if task is None:
                return None

            changes = data.model_dump(exclude_unset=True)

            assignee_id = changes.get("assignee_id")
            if assignee_id is not None:
                assignee = await self.repo.session.get(User, assignee_id)
                if assignee is None:
                    raise InvalidTaskReference("Assignee not found")

            task = await self.repo.update(task, changes)
            return TaskRead.model_validate(task)

    async def delete_task(self, task_id: int) -> bool:
        async with self.repo.session.begin():
            task = await self.repo.get(task_id)
            if task is None:
                return False

            await self.repo.delete(task)
            return True