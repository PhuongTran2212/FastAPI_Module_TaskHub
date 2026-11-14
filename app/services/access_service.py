from app.core.enums import UserRole, WorkspaceRole
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models import User
from app.repositories.workspace_repository import WorkspaceMemberRepository

# Thứ bậc quyền trong workspace: role cao hơn có mọi quyền của role thấp hơn
WORKSPACE_ROLE_RANK = {
    WorkspaceRole.VIEWER: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.OWNER: 3,
}


class AccessService:
    """Kiểm tra quyền của user trên tài nguyên thuộc một workspace."""

    def __init__(self, members: WorkspaceMemberRepository) -> None:
        self.members = members

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
