from app.core import messages
from app.core.enums import ProjectStatus, UserRole, WorkspaceRole
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models import Project, Task, User, Workspace
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.workspace_repository import (
    WorkspaceMemberRepository,
    WorkspaceRepository,
)

# Thứ bậc quyền trong workspace: role cao hơn có mọi quyền của role thấp hơn
WORKSPACE_ROLE_RANK = {
    WorkspaceRole.VIEWER: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.OWNER: 3,
}


class AccessService:
    """Tải tài nguyên trong workspace và kiểm tra quyền của user trên nó.

    Mọi service dùng chung để quy tắc 404/403 giống nhau ở mọi endpoint.
    """

    def __init__(
        self,
        members: WorkspaceMemberRepository,
        workspaces: WorkspaceRepository,
        projects: ProjectRepository,
        tasks: TaskRepository,
    ) -> None:
        self.members = members
        self.workspaces = workspaces
        self.projects = projects
        self.tasks = tasks

    async def require_role(
        self,
        user: User,
        workspace_id: int,
        minimum: WorkspaceRole,
        *,
        resource: str,
    ) -> WorkspaceRole:
        """Trả về role hiệu lực của user trong workspace.

        - ADMIN (role hệ thống) được coi như OWNER của mọi workspace.
        - Không phải member: 404 `resource`, không lộ tài nguyên có tồn tại.
        - Là member nhưng role thấp hơn `minimum`: 403.
        """
        if user.role == UserRole.ADMIN:
            return WorkspaceRole.OWNER

        member = await self.members.get_member(workspace_id, user.id)
        if member is None:
            raise NotFoundException(resource)

        if WORKSPACE_ROLE_RANK[member.role] < WORKSPACE_ROLE_RANK[minimum]:
            raise ForbiddenException()

        return member.role

    async def get_workspace(
        self,
        user: User,
        workspace_id: int,
        minimum: WorkspaceRole,
    ) -> Workspace:
        workspace = await self.workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundException("Workspace")
        await self.require_role(user, workspace.id, minimum, resource="Workspace")
        return workspace

    async def get_project(
        self,
        user: User,
        project_id: int,
        minimum: WorkspaceRole,
    ) -> Project:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundException("Project")
        await self.require_role(user, project.workspace_id, minimum, resource="Project")
        return project

    async def get_task(
        self,
        user: User,
        task_id: int,
        minimum: WorkspaceRole,
    ) -> tuple[Task, WorkspaceRole]:
        """Trả về task (đã nạp kèm project) và role hiệu lực của user."""
        task = await self.tasks.get_with_project(task_id)
        if task is None:
            raise NotFoundException("Task")
        role = await self.require_role(
            user, task.project.workspace_id, minimum, resource="Task"
        )
        return task, role

    @staticmethod
    def ensure_writable(project: Project) -> None:
        """Project đã archive: mọi thứ bên trong chỉ được xem."""
        if project.status == ProjectStatus.ARCHIVED:
            raise ConflictException(messages.PROJECT_ARCHIVED)
