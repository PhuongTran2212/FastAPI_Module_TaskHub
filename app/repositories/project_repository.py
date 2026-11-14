from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProjectStatus
from app.models import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Project)

    async def list_by_workspace(
        self,
        workspace_id: int,
        *,
        page: int,
        limit: int,
        status: ProjectStatus | None = None,
    ) -> tuple[list[Project], int]:
        stmt = select(Project).where(Project.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        return await self.paginate(stmt.order_by(Project.id), page=page, limit=limit)
