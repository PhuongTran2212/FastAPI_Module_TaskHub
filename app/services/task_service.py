from app.core.exceptions import NotFoundException
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo

    def list_tasks(self, skip: int, limit: int) -> list[TaskRead]:
        return self.repo.list(skip, limit)

    def get_task(self, task_id: int) -> TaskRead:
        task = self.repo.get(task_id)

        if task is None:
            raise NotFoundException("Task")

        return task

    def create_task(self, data: TaskCreate) -> TaskRead:
        return self.repo.create(data)

    def update_task(self, task_id: int, data: TaskUpdate) -> TaskRead:
        task = self.repo.update(task_id, data)

        if task is None:
            raise NotFoundException("Task")

        return task

    def delete_task(self, task_id: int) -> None:
        if not self.repo.delete(task_id):
            raise NotFoundException("Task")