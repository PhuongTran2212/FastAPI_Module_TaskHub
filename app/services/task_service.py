from app.core import messages
from app.core.enums import TaskPriority, TaskStatus, WorkspaceRole
from app.core.exceptions import (
    ForbiddenException,
    UnprocessableException,
)
from app.models import User
from app.repositories.task_repository import TaskRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate
from app.services.access_service import AccessService
from app.services.base import TransactionalService

# Người được giao task phải sửa được task đó (VIEWER chỉ xem)
ASSIGNABLE_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.EDITOR}


class TaskService(TransactionalService):
    conflict_message = messages.TASK_CONFLICT

    def __init__(
        self,
        repo: TaskRepository,
        members: WorkspaceMemberRepository,
        access: AccessService,
    ) -> None:
        super().__init__(repo.session)
        self.repo = repo
        self.members = members
        self.access = access

    async def list_tasks(
        self,
        user: User,
        project_id: int,
        *,
        page: int,
        limit: int,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> TaskPage:
        async with self.transaction():
            await self.access.get_project(user, project_id, WorkspaceRole.VIEWER)
            items, total = await self.repo.list_filtered(
                project_id=project_id,
                page=page,
                limit=limit,
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

    async def get_task(self, user: User, task_id: int) -> TaskRead:
        async with self.transaction():
            task, _ = await self.access.get_task(user, task_id, WorkspaceRole.VIEWER)
            return TaskRead.model_validate(task)

    async def create_task(
        self,
        user: User,
        project_id: int,
        data: TaskCreate,
    ) -> TaskRead:
        async with self.transaction():
            project = await self.access.get_project(
                user, project_id, WorkspaceRole.EDITOR
            )
            self.access.ensure_writable(project)
            if data.assignee_id is not None:
                await self._ensure_assignable(project.workspace_id, data.assignee_id)

            values = data.model_dump()
            values["project_id"] = project.id
            values["status"] = TaskStatus.TODO
            values["created_by"] = user.id

            task = await self.repo.create(values)
            return TaskRead.model_validate(task)

    async def update_task(
        self,
        user: User,
        task_id: int,
        data: TaskUpdate,
    ) -> TaskRead:
        async with self.transaction():
            task, _ = await self.access.get_task(user, task_id, WorkspaceRole.EDITOR)
            self.access.ensure_writable(task.project)

            changes = data.model_dump(exclude_unset=True)
            assignee_id = changes.get("assignee_id")
            if assignee_id is not None:
                await self._ensure_assignable(task.project.workspace_id, assignee_id)

            task = await self.repo.update(task, changes)
            return TaskRead.model_validate(task)

    async def delete_task(self, user: User, task_id: int) -> None:
        async with self.transaction():
            task, role = await self.access.get_task(user, task_id, WorkspaceRole.EDITOR)
            # Resource ownership: EDITOR chỉ xóa task do mình tạo,
            # OWNER của workspace (và ADMIN) xóa được mọi task
            if role != WorkspaceRole.OWNER and task.created_by != user.id:
                raise ForbiddenException(messages.TASK_DELETE_NOT_ALLOWED)
            self.access.ensure_writable(task.project)

            await self.repo.delete(task)

    # ---------- Helpers ----------

    async def _ensure_assignable(self, workspace_id: int, user_id: int) -> None:
        member = await self.members.get_member(workspace_id, user_id)
        if member is None or member.role not in ASSIGNABLE_ROLES:
            raise UnprocessableException(messages.ASSIGNEE_NOT_ALLOWED)
