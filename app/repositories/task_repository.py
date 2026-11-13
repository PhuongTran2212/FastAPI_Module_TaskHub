from datetime import UTC, datetime

from app.core.constants import DEFAULT_PAGE_LIMIT
from app.core.enums import TaskStatus
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate


class TaskRepository:
    def __init__(self) -> None:
        self._items: dict[int, TaskRead] = {}
        self._next_id = 1

    def list(
        self,
        skip: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[TaskRead]:
        return list(self._items.values())[skip : skip + limit]

    def get(self, task_id: int) -> TaskRead | None:
        return self._items.get(task_id)

    def create(self, data: TaskCreate) -> TaskRead:
        task = TaskRead(
            id=self._next_id,
            status=TaskStatus.TODO,
            created_at=datetime.now(UTC),
            **data.model_dump(),
        )

        self._items[task.id] = task
        self._next_id += 1

        return task

    def update(
        self,
        task_id: int,
        data: TaskUpdate,
    ) -> TaskRead | None:
        task = self._items.get(task_id)

        if task is None:
            return None

        changes = data.model_dump(exclude_unset=True)
        updated = task.model_copy(update=changes)

        self._items[task_id] = updated

        return updated

    def delete(self, task_id: int) -> bool:
        return self._items.pop(task_id, None) is not None