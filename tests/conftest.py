from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_task_repository
from app.main import app
from app.repositories.task_repository import TaskRepository


@pytest.fixture
def client() -> Iterator[TestClient]:
    repository = TaskRepository()
    previous_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[get_task_repository] = lambda: repository

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)