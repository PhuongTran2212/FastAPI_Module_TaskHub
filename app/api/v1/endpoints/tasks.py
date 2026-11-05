from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import TaskServiceDep
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate
from app.services.task_service import InvalidTaskReference


router = APIRouter()


@router.get("", response_model=TaskPage)
async def list_tasks(
    service: TaskServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    project_id: int | None = Query(None, gt=0),
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: int | None = Query(None, gt=0),
):
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
)
async def create_task(data: TaskCreate, service: TaskServiceDep):
    try:
        return await service.create_task(data)
    except InvalidTaskReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Task data conflicts with database constraints",
        ) from exc


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, service: TaskServiceDep):
    task = await service.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    service: TaskServiceDep,
):
    try:
        task = await service.update_task(task_id, data)
    except InvalidTaskReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Task data conflicts with database constraints",
        ) from exc

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, service: TaskServiceDep):
    try:
        deleted = await service.delete_task(task_id)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Task is still referenced",
        ) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)