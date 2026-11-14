from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, LabelServiceDep
from app.api.responses import (
    AUTH_RESPONSES,
    VALIDATION_RESPONSES,
    conflict_response,
    not_found_response,
)
from app.core import messages
from app.schemas.label import LabelRead, LabelUpdate

router = APIRouter()

# Tạo và liệt kê label nằm ở /projects/{project_id}/labels (endpoints/projects.py)
LABEL_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Label"),
    **conflict_response(f"{messages.LABEL_NAME_EXISTS} / {messages.PROJECT_ARCHIVED}"),
}


@router.patch(
    "/{label_id}",
    response_model=LabelRead,
    summary="Rename or recolor a label (EDITOR)",
    responses=LABEL_RESPONSES,
)
async def update_label(
    label_id: int,
    data: LabelUpdate,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> LabelRead:
    return await service.update(current_user, label_id, data)


@router.delete(
    "/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a label and remove it from every task (EDITOR)",
    responses=LABEL_RESPONSES,
)
async def delete_label(
    label_id: int,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> Response:
    await service.delete(current_user, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
