from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CurrentUser,
    LabelServiceDep,
    ProjectServiceDep,
    TaskServiceDep,
)
from app.api.pagination import PaginationDep
from app.api.responses import (
    AUTH_RESPONSES,
    VALIDATION_RESPONSES,
    conflict_response,
    not_found_response,
)
from app.core import messages
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.label import LabelCreate, LabelRead
from app.schemas.project import ProjectRead, ProjectUpdate
from app.schemas.task import TaskCreate, TaskPage, TaskRead

router = APIRouter()

PROJECT_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Project"),
}


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project (any member)",
    responses=PROJECT_RESPONSES,
)
async def get_project(
    project_id: int,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    return await service.get(current_user, project_id)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update or archive a project (EDITOR)",
    description=(
        'Send `{"status": "ARCHIVED"}` to archive and `{"status": "ACTIVE"}` to '
        "restore. Tasks of an archived project are read-only."
    ),
    responses=PROJECT_RESPONSES,
)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    return await service.update(current_user, project_id, data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a project and its tasks (OWNER)",
    responses=PROJECT_RESPONSES,
)
async def delete_project(
    project_id: int,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> Response:
    await service.delete(current_user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Tasks of a project ----------
@router.get(
    "/{project_id}/tasks",
    response_model=TaskPage,
    summary="List tasks of a project with filters (any member)",
    responses=PROJECT_RESPONSES,
)
async def list_project_tasks(
    project_id: int,
    current_user: CurrentUser,
    service: TaskServiceDep,
    pagination: PaginationDep,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
) -> TaskPage:
    return await service.list_tasks(
        current_user,
        project_id,
        page=pagination.page,
        limit=pagination.limit,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
    )


@router.post(
    "/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task in a project (EDITOR)",
    description=(
        "The task starts as TODO and `created_by` is the current user. "
        "`assignee_id` must be an OWNER or EDITOR member of the workspace."
    ),
    responses={
        **PROJECT_RESPONSES,
        **conflict_response(f"{messages.PROJECT_ARCHIVED} / {messages.TASK_CONFLICT}"),
    },
)
async def create_task(
    project_id: int,
    data: TaskCreate,
    current_user: CurrentUser,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.create_task(current_user, project_id, data)


# ---------- Labels of a project ----------
@router.get(
    "/{project_id}/labels",
    response_model=list[LabelRead],
    summary="List labels of a project (any member)",
    responses=PROJECT_RESPONSES,
)
async def list_labels(
    project_id: int,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> list[LabelRead]:
    return await service.list_for_project(current_user, project_id)


@router.post(
    "/{project_id}/labels",
    response_model=LabelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a label in a project (EDITOR)",
    responses={
        **PROJECT_RESPONSES,
        **conflict_response(
            f"{messages.LABEL_NAME_EXISTS} / {messages.PROJECT_ARCHIVED}"
        ),
    },
)
async def create_label(
    project_id: int,
    data: LabelCreate,
    current_user: CurrentUser,
    service: LabelServiceDep,
) -> LabelRead:
    return await service.create(current_user, project_id, data)
