from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import TaskServiceDep
from app.core.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.error import ErrorResponse
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate


router = APIRouter()

VALIDATION_RESPONSES = {
    422: {
        "description": "Invalid request data or task reference",
    },
}

TASK_RESPONSES = {
    **VALIDATION_RESPONSES,
    404: {
        "model": ErrorResponse,
        "description": "Task not found",
    },
}

CONFLICT_RESPONSES = {
    409: {
        "model": ErrorResponse,
        "description": "Task data conflicts with database constraints",
    },
}


@router.get(
    "",
    response_model=TaskPage,
    summary="List tasks",
    responses=VALIDATION_RESPONSES,
)
async def list_tasks(
    service: TaskServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_PAGE_LIMIT),
    ] = DEFAULT_PAGE_LIMIT,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
) -> TaskPage:
    return await service.list_tasks(
        page=page,
        limit=limit,
        project_id=project_id,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
    )


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses={
        **VALIDATION_RESPONSES,
        **CONFLICT_RESPONSES,
    },
)
async def create_task(
    data: TaskCreate,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.create_task(data)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses=TASK_RESPONSES,
)
async def get_task(
    task_id: int,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.get_task(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    responses={
        **TASK_RESPONSES,
        **CONFLICT_RESPONSES,
    },
)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    service: TaskServiceDep,
) -> TaskRead:
    return await service.update_task(task_id, data)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a task",
    responses={
        **TASK_RESPONSES,
        **CONFLICT_RESPONSES,
    },
)
async def delete_task(
    task_id: int,
    service: TaskServiceDep,
) -> Response:
    await service.delete_task(task_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)