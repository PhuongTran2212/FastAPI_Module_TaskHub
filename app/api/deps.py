from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.repositories.task_repository import TaskRepository
from app.services.task_service import TaskService


@lru_cache
def get_task_repository() -> TaskRepository:
    # lru_cache => chỉ tạo 1 instance (singleton) để dữ liệu in-memory được giữ lại
    return TaskRepository()


def get_task_service(
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
) -> TaskService:
    return TaskService(repo)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]