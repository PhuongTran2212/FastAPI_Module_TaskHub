from fastapi import APIRouter, Response, status

from app.api.deps import CommentServiceDep, CurrentUser
from app.api.responses import (
    AUTH_RESPONSES,
    VALIDATION_RESPONSES,
    conflict_response,
    not_found_response,
)
from app.core import messages

router = APIRouter()

# Thêm và liệt kê comment nằm ở /tasks/{task_id}/comments (endpoints/tasks.py)


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a comment (its author, or the workspace OWNER)",
    responses={
        **VALIDATION_RESPONSES,
        **AUTH_RESPONSES,
        **not_found_response("Comment"),
        **conflict_response(messages.PROJECT_ARCHIVED),
    },
)
async def delete_comment(
    comment_id: int,
    current_user: CurrentUser,
    service: CommentServiceDep,
) -> Response:
    await service.delete(current_user, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
