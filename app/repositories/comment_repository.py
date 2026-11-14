from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Comment, Task
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Comment)

    async def list_for_task(
        self,
        task_id: int,
        *,
        page: int,
        limit: int,
    ) -> tuple[list[Comment], int]:
        stmt = select(Comment).where(Comment.task_id == task_id).order_by(Comment.id)
        return await self.paginate(stmt, page=page, limit=limit)

    async def get_with_project(self, comment_id: int) -> Comment | None:
        # Nạp kèm task và project để biết workspace và trạng thái archive
        stmt = (
            select(Comment)
            .options(joinedload(Comment.task).joinedload(Task.project))
            .where(Comment.id == comment_id)
        )
        return await self.session.scalar(stmt)
