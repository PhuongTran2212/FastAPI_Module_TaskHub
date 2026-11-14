from app.core import messages
from app.core.enums import WorkspaceRole
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models import User
from app.repositories.comment_repository import CommentRepository
from app.schemas.comment import CommentCreate, CommentPage, CommentRead
from app.services.access_service import AccessService
from app.services.base import TransactionalService


class CommentService(TransactionalService):
    def __init__(self, comments: CommentRepository, access: AccessService) -> None:
        super().__init__(comments.session)
        self.comments = comments
        self.access = access

    async def list_for_task(
        self,
        user: User,
        task_id: int,
        *,
        page: int,
        limit: int,
    ) -> CommentPage:
        async with self.transaction():
            await self.access.get_task(user, task_id, WorkspaceRole.VIEWER)
            items, total = await self.comments.list_for_task(
                task_id, page=page, limit=limit
            )
            return CommentPage(
                items=[CommentRead.model_validate(item) for item in items],
                total=total,
                page=page,
                limit=limit,
            )

    async def create(
        self,
        user: User,
        task_id: int,
        data: CommentCreate,
    ) -> CommentRead:
        async with self.transaction():
            task, _ = await self.access.get_task(user, task_id, WorkspaceRole.EDITOR)
            self.access.ensure_writable(task.project)
            comment = await self.comments.create(
                {"task_id": task.id, "author_id": user.id, "content": data.content}
            )
            return CommentRead.model_validate(comment)

    async def delete(self, user: User, comment_id: int) -> None:
        async with self.transaction():
            comment = await self.comments.get_with_project(comment_id)
            if comment is None:
                raise NotFoundException("Comment")
            project = comment.task.project
            role = await self.access.require_role(
                user, project.workspace_id, WorkspaceRole.EDITOR, resource="Comment"
            )
            # Resource ownership: chỉ tác giả hoặc OWNER (và ADMIN) được xóa
            if role != WorkspaceRole.OWNER and comment.author_id != user.id:
                raise ForbiddenException(messages.COMMENT_DELETE_NOT_ALLOWED)
            self.access.ensure_writable(project)

            await self.comments.delete(comment)
