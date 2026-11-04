from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import TaskServiceDep
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter()


@router.get("", response_model=list[TaskRead])
def list_tasks(
    service: TaskServiceDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return service.list_tasks(skip, limit)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, service: TaskServiceDep):
    return service.create_task(data)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, service: TaskServiceDep):
    task = service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, data: TaskUpdate, service: TaskServiceDep):
    task = service.update_task(task_id, data)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, service: TaskServiceDep):
    if not service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")