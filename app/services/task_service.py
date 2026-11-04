from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo

    def list_tasks(self, skip: int, limit: int) -> list[TaskRead]:
        return self.repo.list(skip, limit)

    def get_task(self, task_id: int) -> TaskRead | None:
        return self.repo.get(task_id)

    def create_task(self, data: TaskCreate) -> TaskRead:
        return self.repo.create(data)

    def update_task(self, task_id: int, data: TaskUpdate) -> TaskRead | None:
        return self.repo.update(task_id, data)

    def delete_task(self, task_id: int) -> bool:
        return self.repo.delete(task_id)