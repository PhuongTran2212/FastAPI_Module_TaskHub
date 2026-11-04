from datetime import UTC, datetime

from app.schemas.task import TaskCreate, TaskRead, TaskUpdate


class TaskRepository:
    def __init__(self) -> None:
        self._items: dict[int, TaskRead] = {}
        self._next_id = 1

    def list(self, skip: int = 0, limit: int = 20) -> list[TaskRead]:
        return list(self._items.values())[skip : skip + limit]

    def get(self, task_id: int) -> TaskRead | None:
        return self._items.get(task_id)

    def create(self, data: TaskCreate) -> TaskRead:
        task = TaskRead(
            id=self._next_id,
            created_at=datetime.now(UTC),
            **data.model_dump(),
        )
        self._items[task.id] = task
        self._next_id += 1
        return task

    def update(self, task_id: int, data: TaskUpdate) -> TaskRead | None:
        task = self._items.get(task_id)
        if task is None:
            return None
        updated = task.model_copy(update=data.model_dump(exclude_unset=True))
        self._items[task_id] = updated
        return updated

    def delete(self, task_id: int) -> bool:
        return self._items.pop(task_id, None) is not None