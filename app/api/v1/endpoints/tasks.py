from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, LabelServiceDep, TaskServiceDep
from app.api.responses import (
    AUTH_RESPONSES,
    VALIDATION_RESPONSES,
    conflict_response,
    not_found_response,
)
from app.core import messages
from app.schemas.label import LabelRead
from app.schemas.task import TaskRead, TaskUpdate

router = APIRouter()

# Tạo và liệt kê task nằm ở /projects/{project_id}/tasks (endpoints/projects.py)
TASK_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Task"),
}
TASK_WRITE_RESPONSES = {
    **TASK_RESPONSES,
    **conflict_response(f"{messages.PROJECT_ARCHIVED} / {messages.TASK_CONFLICT}"),
}


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task (any member)",
    responses=TASK_RESPONSES,
)
async def get_task(
    task_id: int,
    current_user: CurrentUser,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.get_task(current_user, task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update, assign or move a task through statuses (EDITOR)",
    description=(
        "`assignee_id` must be an OWNER or EDITOR member of the task's workspace; "
        "send `null` to unassign."
    ),
    responses=TASK_WRITE_RESPONSES,
)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    current_user: CurrentUser,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.update_task(current_user, task_id, data)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a task (its creator, or the workspace OWNER)",
    responses=TASK_WRITE_RESPONSES,
)
async def delete_task(
    task_id: int,
    current_user: CurrentUser,
    service: TaskServiceDep,
) -> Response:
    await service.delete_task(current_user, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Labels of a task ----------
TASK_LABEL_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Task", "Label"),
    **conflict_response(messages.PROJECT_ARCHIVED),
}


@router.get(
    "/{task_id}/labels",
    response_model=list[LabelRead],
    summary="List labels attached to a task (any member)",
    responses=TASK_RESPONSES,
)
async def list_task_labels(
    task_id: int,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> list[LabelRead]:
    return await service.list_for_task(current_user, task_id)


@router.post(
    "/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Attach a label of the same project to a task (EDITOR)",
    description="Idempotent: attaching an already attached label is a no-op.",
    responses=TASK_LABEL_RESPONSES,
)
async def attach_label(
    task_id: int,
    label_id: int,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> Response:
    await service.attach(current_user, task_id, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Detach a label from a task (EDITOR)",
    description="Idempotent: detaching a label that is not attached is a no-op.",
    responses=TASK_LABEL_RESPONSES,
)
async def detach_label(
    task_id: int,
    label_id: int,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> Response:
    await service.detach(current_user, task_id, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
