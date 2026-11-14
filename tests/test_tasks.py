from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core import messages
from app.core.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, TASK_TITLE_MAX_LENGTH

URL = "/api/v1/tasks"
MISSING_ID = 999_999_999


def project_tasks(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/tasks"


async def create_task(
    client: AsyncClient,
    seed_data: dict,
    project_id: int | None = None,
    **fields,
) -> dict:
    response = await client.post(
        project_tasks(project_id or seed_data["project_id"]),
        json={"title": "Task test", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_task_crud(client, seed_data):
    list_url = project_tasks(seed_data["project_id"])
    task = await create_task(client, seed_data, title="  Learn FastAPI  ")
    assert task["title"] == "Learn FastAPI"
    assert task["status"] == "TODO"
    assert task["priority"] == "MEDIUM"
    assert task["project_id"] == seed_data["project_id"]
    assert task["created_by"] == seed_data["creator_id"]
    assert task["created_at"]
    path = f"{URL}/{task['id']}"
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json() == task
    response = await client.get(list_url)
    assert response.status_code == 200
    assert response.json() == {
        "items": [task],
        "total": 1,
        "page": 1,
        "limit": DEFAULT_PAGE_LIMIT,
    }
    response = await client.patch(path, json={"status": "DONE", "title": "  Done  "})
    assert response.status_code == 200
    updated = response.json()
    assert updated == {**task, "status": "DONE", "title": "Done"}
    assert (await client.get(path)).json() == updated
    response = await client.delete(path)
    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(path)).status_code == 404
    assert (await client.get(list_url)).json()["total"] == 0


async def test_each_test_has_no_tasks(client, seed_data):
    response = await client.get(project_tasks(seed_data["project_id"]))
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_task_not_found(client, method):
    kwargs = {"json": {"status": "DONE"}} if method == "PATCH" else {}
    response = await client.request(method, f"{URL}/{MISSING_ID}", **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_project_tasks_of_missing_project(client, method):
    kwargs = {"json": {"title": "Task"}} if method == "POST" else {}
    response = await client.request(method, project_tasks(MISSING_ID), **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    "title", ["", "   ", "\t\n", "a" * (TASK_TITLE_MAX_LENGTH + 1), None]
)
async def test_invalid_title(client, seed_data, method, title):
    if method == "POST":
        path = project_tasks(seed_data["project_id"])
    else:
        task = await create_task(client, seed_data)
        path = f"{URL}/{task['id']}"
    response = await client.request(method, path, json={"title": title})
    assert response.status_code == 422
    assert any("title" in error["loc"] for error in response.json()["detail"])


async def test_title_boundary(client, seed_data):
    title = "a" * TASK_TITLE_MAX_LENGTH
    task = await create_task(client, seed_data, title=title)
    assert task["title"] == title
    response = await client.patch(f"{URL}/{task['id']}", json={"title": title})
    assert response.status_code == 200


async def test_create_requires_title(client, seed_data):
    response = await client.post(project_tasks(seed_data["project_id"]), json={})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["title", "status", "priority"])
async def test_patch_rejects_null(client, seed_data, field):
    task = await create_task(client, seed_data)
    path = f"{URL}/{task['id']}"
    response = await client.patch(path, json={field: None})
    assert response.status_code == 422
    assert (await client.get(path)).json() == task


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "TODO"),
        ("status", "DONE"),
        ("status", None),
        ("project_id", 1),
        ("created_by", 1),
    ],
)
async def test_create_rejects_server_controlled_fields(client, seed_data, field, value):
    list_url = project_tasks(seed_data["project_id"])
    response = await client.post(list_url, json={"title": "Task", field: value})
    assert response.status_code == 422
    assert (await client.get(list_url)).json()["total"] == 0


@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_reject_past_due_date(client, seed_data, method):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    list_url = project_tasks(seed_data["project_id"])
    if method == "POST":
        path = list_url
        payload = {"title": "Task"}
    else:
        task = await create_task(client, seed_data)
        path = f"{URL}/{task['id']}"
        payload = {}
    response = await client.request(
        method, path, json={**payload, "due_date": yesterday}
    )
    assert response.status_code == 422
    if method == "PATCH":
        assert (await client.get(path)).json() == task
    else:
        assert (await client.get(list_url)).json()["total"] == 0


@pytest.mark.parametrize("days", [0, 1])
async def test_accept_today_and_future(client, seed_data, days):
    due_date = (date.today() + timedelta(days=days)).isoformat()
    task = await create_task(client, seed_data, due_date=due_date)
    assert task["due_date"] == due_date
    response = await client.patch(f"{URL}/{task['id']}", json={"due_date": due_date})
    assert response.status_code == 200
    assert response.json()["due_date"] == due_date


async def test_overdue_task_can_be_read_and_updated(client, seed_data, monkeypatch):
    from app.schemas import task as task_schema

    today = date.today()
    task = await create_task(client, seed_data, due_date=today.isoformat())

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return today + timedelta(days=1)

    monkeypatch.setattr(task_schema, "date", Tomorrow)
    path = f"{URL}/{task['id']}"
    assert (await client.get(path)).status_code == 200
    response = await client.patch(path, json={"status": "DONE"})
    assert response.status_code == 200
    assert response.json()["due_date"] == today.isoformat()


async def test_empty_patch_preserves_task(client, seed_data):
    task = await create_task(client, seed_data)
    response = await client.patch(f"{URL}/{task['id']}", json={})
    assert response.status_code == 200
    assert response.json() == task


async def test_patch_can_clear_nullable_fields(client, seed_data):
    task = await create_task(
        client,
        seed_data,
        description="Description",
        assignee_id=seed_data["assignee_id"],
        due_date=(date.today() + timedelta(days=1)).isoformat(),
    )
    path = f"{URL}/{task['id']}"
    response = await client.patch(
        path, json={"description": None, "due_date": None, "assignee_id": None}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated == {
        **task,
        "description": None,
        "due_date": None,
        "assignee_id": None,
    }
    assert (await client.get(path)).json() == updated


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    "payload", [{"priority": "INVALID"}, {"due_date": "not-a-date"}]
)
async def test_invalid_values(client, seed_data, method, payload):
    if method == "POST":
        path = project_tasks(seed_data["project_id"])
        payload = {"title": "Task", **payload}
    else:
        task = await create_task(client, seed_data)
        path = f"{URL}/{task['id']}"
    assert (await client.request(method, path, json=payload)).status_code == 422


async def test_patch_rejects_invalid_status(client, seed_data):
    task = await create_task(client, seed_data)
    response = await client.patch(f"{URL}/{task['id']}", json={"status": "INVALID"})
    assert response.status_code == 422


async def test_create_rejects_assignee_outside_workspace(client, seed_data):
    list_url = project_tasks(seed_data["project_id"])
    response = await client.post(
        list_url, json={"title": "Task", "assignee_id": MISSING_ID}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": messages.ASSIGNEE_NOT_ALLOWED}
    await create_task(client, seed_data)
    assert (await client.get(list_url)).json()["total"] == 1


async def test_patch_rejects_assignee_outside_workspace(client, seed_data):
    task = await create_task(client, seed_data)
    path = f"{URL}/{task['id']}"
    response = await client.patch(path, json={"assignee_id": MISSING_ID})
    assert response.status_code == 422
    assert response.json() == {"detail": messages.ASSIGNEE_NOT_ALLOWED}
    assert (await client.get(path)).json() == task


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page": "abc"},
        {"limit": 0},
        {"limit": MAX_PAGE_LIMIT + 1},
        {"assignee_id": 0},
        {"status": "INVALID"},
        {"priority": "INVALID"},
    ],
)
async def test_invalid_pagination_and_filters(client, seed_data, params):
    response = await client.get(project_tasks(seed_data["project_id"]), params=params)
    assert response.status_code == 422


async def test_pagination(client, seed_data):
    list_url = project_tasks(seed_data["project_id"])
    tasks = [
        await create_task(client, seed_data, title=f"Task {i}")
        for i in range(DEFAULT_PAGE_LIMIT + 1)
    ]
    response = await client.get(list_url)
    assert response.status_code == 200
    assert response.json() == {
        "items": tasks[:DEFAULT_PAGE_LIMIT],
        "total": len(tasks),
        "page": 1,
        "limit": DEFAULT_PAGE_LIMIT,
    }
    response = await client.get(list_url, params={"page": 2})
    assert response.json()["items"] == tasks[DEFAULT_PAGE_LIMIT:]
    assert response.json()["total"] == len(tasks)
    response = await client.get(list_url, params={"page": 100})
    assert response.json()["items"] == []
    assert response.json()["total"] == len(tasks)
    assert (await client.get(list_url, params={"limit": MAX_PAGE_LIMIT})).json()[
        "items"
    ] == tasks


async def test_filters_and_filtered_total(client, seed_data):
    list_url = project_tasks(seed_data["project_id"])
    task = await create_task(
        client, seed_data, priority="HIGH", assignee_id=seed_data["assignee_id"]
    )
    task = (await client.patch(f"{URL}/{task['id']}", json={"status": "DONE"})).json()
    await create_task(client, seed_data)
    other = await create_task(
        client,
        seed_data,
        project_id=seed_data["other_project_id"],
        priority="HIGH",
        assignee_id=seed_data["assignee_id"],
    )
    for params in (
        {"status": "DONE"},
        {"priority": "HIGH"},
        {"assignee_id": seed_data["assignee_id"]},
        {"status": "DONE", "priority": "HIGH", "assignee_id": seed_data["assignee_id"]},
    ):
        response = await client.get(list_url, params={**params, "limit": 1})
        assert response.status_code == 200
        assert response.json()["items"] == [task]
        assert response.json()["total"] == 1
    # Mỗi project chỉ trả task của chính nó
    response = await client.get(project_tasks(seed_data["other_project_id"]))
    assert response.json()["items"] == [other]
    response = await client.get(list_url, params={"status": "IN_REVIEW"})
    assert response.json()["total"] == 0


@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_database_conflict_returns_409_and_rolls_back(
    client, seed_data, db_connection, method
):
    list_url = project_tasks(seed_data["project_id"])
    task = await create_task(client, seed_data)
    # A real constraint triggers IntegrityError without mocking CRUD.
    await db_connection.execute(
        text(
            "ALTER TABLE tasks ADD CONSTRAINT ck_test_title "
            "CHECK (title <> 'constraint-conflict')"
        )
    )
    path = list_url if method == "POST" else f"{URL}/{task['id']}"
    response = await client.request(method, path, json={"title": "constraint-conflict"})
    assert response.status_code == 409
    assert response.json() == {"detail": messages.TASK_CONFLICT}
    assert (await client.get(f"{URL}/{task['id']}")).json() == task
    await create_task(client, seed_data, title="Valid after conflict")
    assert (await client.get(list_url)).json()["total"] == 2


async def test_delete_database_conflict_returns_409(client, seed_data, db_connection):
    task = await create_task(client, seed_data)
    await db_connection.execute(
        text(
            "CREATE TABLE review_test_task_references ("
            "task_id INTEGER REFERENCES tasks(id) ON DELETE RESTRICT)"
        )
    )
    await db_connection.execute(
        text("INSERT INTO review_test_task_references (task_id) VALUES (:id)"),
        {"id": task["id"]},
    )
    response = await client.delete(f"{URL}/{task['id']}")
    assert response.status_code == 409
    assert response.json() == {"detail": messages.TASK_CONFLICT}
    assert (await client.get(f"{URL}/{task['id']}")).json() == task


async def test_openapi_contract(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    create = spec["components"]["schemas"]["TaskCreate"]
    assert "status" not in create["properties"]
    assert "project_id" not in create["properties"]
    assert create["additionalProperties"] is False
    list_path = "/api/v1/projects/{project_id}/tasks"
    task_path = URL + "/{task_id}"
    expected = [
        ("get", list_path, "200"),
        ("post", list_path, "201"),
        ("get", task_path, "200"),
        ("patch", task_path, "200"),
        ("delete", task_path, "204"),
    ]
    for method, path, success in expected:
        operation = spec["paths"][path][method]
        assert operation["summary"]
        assert operation["security"] == [{"HTTPBearer": []}]
        for code in (success, "401", "403", "404", "422"):
            assert code in operation["responses"]
    for method, path in (("post", list_path), ("patch", task_path)):
        assert "409" in spec["paths"][path][method]["responses"]
    assert "content" not in spec["paths"][task_path]["delete"]["responses"]["204"]
    # Đường dẫn cũ của Day 3 đã chuyển vào /projects/{project_id}/tasks
    assert URL not in spec["paths"]
