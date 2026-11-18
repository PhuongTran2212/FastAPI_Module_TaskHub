from app.core import messages
from app.core.enums import WorkspaceRole
from app.core.exceptions import NotFoundException
from app.models import Label, Task, User
from app.repositories.label_repository import LabelRepository
from app.schemas.label import LabelCreate, LabelRead, LabelUpdate
from app.services.access_service import AccessService
from app.services.base import TransactionalService


class LabelService(TransactionalService):
    # Lỗi ràng buộc duy nhất có thể xảy ra: trùng (project_id, name)
    conflict_message = messages.LABEL_NAME_EXISTS

    def __init__(self, labels: LabelRepository, access: AccessService) -> None:
        super().__init__(labels.session)
        self.labels = labels
        self.access = access

    # ---------- Labels of a project ----------
    async def list_for_project(self, user: User, project_id: int) -> list[LabelRead]:
        async with self.transaction():
            await self.access.get_project(user, project_id, WorkspaceRole.VIEWER)
            labels = await self.labels.list_by_project(project_id)
            return [LabelRead.model_validate(label) for label in labels]

    async def create(
        self,
        user: User,
        project_id: int,
        data: LabelCreate,
    ) -> LabelRead:
        async with self.transaction():
            project = await self.access.get_project(
                user, project_id, WorkspaceRole.EDITOR
            )
            self.access.ensure_writable(project)
            label = await self.labels.create(
                {**data.model_dump(), "project_id": project.id}
            )
            return LabelRead.model_validate(label)

    async def update(self, user: User, label_id: int, data: LabelUpdate) -> LabelRead:
        async with self.transaction():
            label = await self._get_label(user, label_id, WorkspaceRole.EDITOR)
            self.access.ensure_writable(label.project)
            label = await self.labels.update(label, data.model_dump(exclude_unset=True))
            return LabelRead.model_validate(label)

    async def delete(self, user: User, label_id: int) -> None:
        async with self.transaction():
            label = await self._get_label(user, label_id, WorkspaceRole.EDITOR)
            self.access.ensure_writable(label.project)
            # FK ON DELETE CASCADE bỏ label khỏi mọi task
            await self.labels.delete(label)

    # ---------- Labels of a task ----------
    async def list_for_task(self, user: User, task_id: int) -> list[LabelRead]:
        async with self.transaction():
            await self.access.get_task(user, task_id, WorkspaceRole.VIEWER)
            labels = await self.labels.list_for_task(task_id)
            return [LabelRead.model_validate(label) for label in labels]

    async def attach(self, user: User, task_id: int, label_id: int) -> None:
        async with self.transaction():
            task = await self._get_writable_task(user, task_id)
            await self._get_label_of_task_project(task, label_id)
            await self.labels.attach(task.id, label_id)

    async def detach(self, user: User, task_id: int, label_id: int) -> None:
        async with self.transaction():
            task = await self._get_writable_task(user, task_id)
            await self._get_label_of_task_project(task, label_id)
            await self.labels.detach(task.id, label_id)

    # ---------- Helpers ----------
    async def _get_label(
        self,
        user: User,
        label_id: int,
        minimum: WorkspaceRole,
    ) -> Label:
        label = await self.labels.get_with_project(label_id)
        if label is None:
            raise NotFoundException("Label")
        await self.access.require_role(
            user, label.project.workspace_id, minimum, resource="Label"
        )
        return label

    async def _get_writable_task(self, user: User, task_id: int) -> Task:
        task, _ = await self.access.get_task(user, task_id, WorkspaceRole.EDITOR)
        self.access.ensure_writable(task.project)
        return task

    async def _get_label_of_task_project(self, task: Task, label_id: int) -> Label:
        # Label của project khác coi như không tồn tại với task này
        label = await self.labels.get(label_id)
        if label is None or label.project_id != task.project_id:
            raise NotFoundException("Label")
        return label
