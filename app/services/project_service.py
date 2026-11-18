from app.core.enums import ProjectStatus, WorkspaceRole
from app.models import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectPage,
    ProjectRead,
    ProjectUpdate,
)
from app.services.access_service import AccessService
from app.services.base import TransactionalService


class ProjectService(TransactionalService):
    def __init__(
        self,
        projects: ProjectRepository,
        access: AccessService,
    ) -> None:
        super().__init__(projects.session)
        self.projects = projects
        self.access = access

    async def create(
        self,
        user: User,
        workspace_id: int,
        data: ProjectCreate,
    ) -> ProjectRead:
        async with self.transaction():
            await self.access.get_workspace(user, workspace_id, WorkspaceRole.EDITOR)
            project = await self.projects.create(
                {**data.model_dump(), "workspace_id": workspace_id}
            )
            return ProjectRead.model_validate(project)

    async def list_for_workspace(
        self,
        user: User,
        workspace_id: int,
        *,
        page: int,
        limit: int,
        status: ProjectStatus | None = None,
    ) -> ProjectPage:
        async with self.transaction():
            await self.access.get_workspace(user, workspace_id, WorkspaceRole.VIEWER)
            items, total = await self.projects.list_by_workspace(
                workspace_id, page=page, limit=limit, status=status
            )
            return ProjectPage(
                items=[ProjectRead.model_validate(item) for item in items],
                total=total,
                page=page,
                limit=limit,
            )

    async def get(self, user: User, project_id: int) -> ProjectRead:
        async with self.transaction():
            project = await self.access.get_project(
                user, project_id, WorkspaceRole.VIEWER
            )
            return ProjectRead.model_validate(project)

    async def update(
        self,
        user: User,
        project_id: int,
        data: ProjectUpdate,
    ) -> ProjectRead:
        async with self.transaction():
            project = await self.access.get_project(
                user, project_id, WorkspaceRole.EDITOR
            )
            project = await self.projects.update(
                project, data.model_dump(exclude_unset=True)
            )
            return ProjectRead.model_validate(project)

    async def delete(self, user: User, project_id: int) -> None:
        async with self.transaction():
            project = await self.access.get_project(
                user, project_id, WorkspaceRole.OWNER
            )
            # FK ON DELETE CASCADE xóa task, label, comment của project
            await self.projects.delete(project)
