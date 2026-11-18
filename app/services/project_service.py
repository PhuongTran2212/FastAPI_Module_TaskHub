from app.core.enums import ProjectStatus, WorkspaceRole
from app.core.exceptions import NotFoundException
from app.models import Project, User
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
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
        workspaces: WorkspaceRepository,
        access: AccessService,
    ) -> None:
        super().__init__(projects.session)
        self.projects = projects
        self.workspaces = workspaces
        self.access = access

    async def create(
        self,
        user: User,
        workspace_id: int,
        data: ProjectCreate,
    ) -> ProjectRead:
        async with self.transaction():
            await self._require_workspace(user, workspace_id, WorkspaceRole.EDITOR)
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
            await self._require_workspace(user, workspace_id, WorkspaceRole.VIEWER)
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
            project = await self._get_project(user, project_id, WorkspaceRole.VIEWER)
            return ProjectRead.model_validate(project)

    async def update(
        self,
        user: User,
        project_id: int,
        data: ProjectUpdate,
    ) -> ProjectRead:
        async with self.transaction():
            project = await self._get_project(user, project_id, WorkspaceRole.EDITOR)
            project = await self.projects.update(
                project, data.model_dump(exclude_unset=True)
            )
            return ProjectRead.model_validate(project)

    async def delete(self, user: User, project_id: int) -> None:
        async with self.transaction():
            project = await self._get_project(user, project_id, WorkspaceRole.OWNER)
            # FK ON DELETE CASCADE xóa task, label, comment của project
            await self.projects.delete(project)

    async def _require_workspace(
        self,
        user: User,
        workspace_id: int,
        minimum: WorkspaceRole,
    ) -> None:
        if await self.workspaces.get(workspace_id) is None:
            raise NotFoundException("Workspace")
        await self.access.require_role(
            user, workspace_id, minimum, resource="Workspace"
        )

    async def _get_project(
        self,
        user: User,
        project_id: int,
        minimum: WorkspaceRole,
    ) -> Project:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundException("Project")
        await self.access.require_role(
            user, project.workspace_id, minimum, resource="Project"
        )
        return project
