from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Workspace, WorkspaceMember
from app.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Workspace)

    async def list_for_member(
        self,
        user_id: int,
        *,
        page: int,
        limit: int,
    ) -> tuple[list[Workspace], int]:
        stmt = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.id)
        )
        return await self.paginate(stmt, page=page, limit=limit)


class WorkspaceMemberRepository(BaseRepository[WorkspaceMember]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WorkspaceMember)

    async def get_member(
        self,
        workspace_id: int,
        user_id: int,
    ) -> WorkspaceMember | None:
        # Khóa chính ghép (workspace_id, user_id)
        return await self.session.get(WorkspaceMember, (workspace_id, user_id))

    async def list_with_users(self, workspace_id: int) -> list[WorkspaceMember]:
        stmt = (
            select(WorkspaceMember)
            .options(joinedload(WorkspaceMember.user))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.user_id)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())
