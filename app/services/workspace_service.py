from app.core import messages
from app.core.enums import UserRole, WorkspaceRole
from app.core.exceptions import ConflictException, NotFoundException
from app.models import User, Workspace, WorkspaceMember
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workspace_repository import (
    WorkspaceMemberRepository,
    WorkspaceRepository,
)
from app.schemas.workspace import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    WorkspaceCreate,
    WorkspacePage,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services.access_service import AccessService
from app.services.base import TransactionalService


class WorkspaceService(TransactionalService):
    def __init__(
        self,
        workspaces: WorkspaceRepository,
        members: WorkspaceMemberRepository,
        users: UserRepository,
        tasks: TaskRepository,
        access: AccessService,
    ) -> None:
        super().__init__(workspaces.session)
        self.workspaces = workspaces
        self.members = members
        self.users = users
        self.tasks = tasks
        self.access = access

    # ---------- Workspace ----------
    async def create(self, user: User, data: WorkspaceCreate) -> WorkspaceRead:
        async with self.transaction():
            workspace = await self.workspaces.create(
                {"name": data.name, "owner_id": user.id}
            )
            # Người tạo luôn là OWNER; quyền đều kiểm tra qua workspace_members
            await self.members.create(
                {
                    "workspace_id": workspace.id,
                    "user_id": user.id,
                    "role": WorkspaceRole.OWNER,
                }
            )
            return WorkspaceRead.model_validate(workspace)

    async def list_for_user(self, user: User, page: int, limit: int) -> WorkspacePage:
        async with self.transaction():
            if user.role == UserRole.ADMIN:
                items, total = await self.workspaces.list_page(page=page, limit=limit)
            else:
                items, total = await self.workspaces.list_for_member(
                    user.id, page=page, limit=limit
                )
            return WorkspacePage(
                items=[WorkspaceRead.model_validate(item) for item in items],
                total=total,
                page=page,
                limit=limit,
            )

    async def get(self, user: User, workspace_id: int) -> WorkspaceRead:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.VIEWER
            )
            return WorkspaceRead.model_validate(workspace)

    async def update(
        self,
        user: User,
        workspace_id: int,
        data: WorkspaceUpdate,
    ) -> WorkspaceRead:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.OWNER
            )
            workspace = await self.workspaces.update(
                workspace, data.model_dump(exclude_unset=True)
            )
            return WorkspaceRead.model_validate(workspace)

    async def delete(self, user: User, workspace_id: int) -> None:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.OWNER
            )
            # FK ON DELETE CASCADE xóa member, project, task, label, comment
            await self.workspaces.delete(workspace)

    # ---------- Members ----------
    async def list_members(self, user: User, workspace_id: int) -> list[MemberRead]:
        async with self.transaction():
            await self._get_workspace(user, workspace_id, WorkspaceRole.VIEWER)
            members = await self.members.list_with_users(workspace_id)
            return [MemberRead.from_member(member, member.user) for member in members]

    async def add_member(
        self,
        user: User,
        workspace_id: int,
        data: MemberCreate,
    ) -> MemberRead:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.OWNER
            )
            invitee = await self.users.get_by_email(data.email)
            if invitee is None:
                raise NotFoundException("User")
            if await self.members.get_member(workspace.id, invitee.id) is not None:
                raise ConflictException(messages.MEMBER_ALREADY_EXISTS)

            member = await self.members.create(
                {
                    "workspace_id": workspace.id,
                    "user_id": invitee.id,
                    "role": data.role,
                }
            )
            return MemberRead.from_member(member, invitee)

    async def update_member(
        self,
        user: User,
        workspace_id: int,
        member_user_id: int,
        data: MemberUpdate,
    ) -> MemberRead:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.OWNER
            )
            member = await self._get_changeable_member(workspace, member_user_id)
            member = await self.members.update(member, {"role": data.role})
            member_user = await self.users.get(member_user_id)
            if member_user is None:
                raise NotFoundException("Member")
            return MemberRead.from_member(member, member_user)

    async def remove_member(
        self,
        user: User,
        workspace_id: int,
        member_user_id: int,
    ) -> None:
        async with self.transaction():
            workspace = await self._get_workspace(
                user, workspace_id, WorkspaceRole.OWNER
            )
            member = await self._get_changeable_member(workspace, member_user_id)
            # Người rời workspace không còn là assignee hợp lệ của task trong đó
            await self.tasks.unassign_in_workspace(workspace.id, member_user_id)
            await self.members.delete(member)

    # ---------- Helpers ----------
    async def _get_workspace(
        self,
        user: User,
        workspace_id: int,
        minimum: WorkspaceRole,
    ) -> Workspace:
        workspace = await self.workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundException("Workspace")
        await self.access.require_role(
            user, workspace.id, minimum, resource="Workspace"
        )
        return workspace

    async def _get_changeable_member(
        self,
        workspace: Workspace,
        member_user_id: int,
    ) -> WorkspaceMember:
        member = await self.members.get_member(workspace.id, member_user_id)
        if member is None:
            raise NotFoundException("Member")
        if member_user_id == workspace.owner_id:
            raise ConflictException(messages.OWNER_MEMBERSHIP_LOCKED)
        return member
