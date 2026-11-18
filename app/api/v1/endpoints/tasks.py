from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import TaskServiceDep
from app.core.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.schemas.error import ErrorResponse
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate


router = APIRouter()

VALIDATION_RESPONSES = {
    422: {"description": "Invalid request data"},
}

TASK_RESPONSES = {
    **VALIDATION_RESPONSES,
    404: {
        "model": ErrorResponse,
        "description": "Task not found",
    },
}


@router.get(
    "",
    response_model=list[TaskRead],
    summary="List tasks",
    responses=VALIDATION_RESPONSES,
)
def list_tasks(
    service: TaskServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_PAGE_LIMIT),
    ] = DEFAULT_PAGE_LIMIT,
) -> list[TaskRead]:
    return service.list_tasks(skip, limit)


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses=VALIDATION_RESPONSES,
)
def create_task(
    data: TaskCreate,
    service: TaskServiceDep,
) -> TaskRead:
    return service.create_task(data)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses=TASK_RESPONSES,
)
def get_task(
    task_id: int,
    service: TaskServiceDep,
) -> TaskRead:
    return service.get_task(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    responses=TASK_RESPONSES,
)
def update_task(
    task_id: int,
    data: TaskUpdate,
    service: TaskServiceDep,
) -> TaskRead:
    return service.update_task(task_id, data)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a task",
    responses=TASK_RESPONSES,
)
def delete_task(
    task_id: int,
    service: TaskServiceDep,
) -> Response:
    service.delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)