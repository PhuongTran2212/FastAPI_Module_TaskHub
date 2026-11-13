import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

URL = "/api/v1/tasks"


def test_task_crud(client: TestClient):
    # Create
    response = client.post(
        URL,
        json={"title": "  Học FastAPI  "},
    )
    assert response.status_code == 201

    task = response.json()
    assert task["title"] == "Học FastAPI"
    assert task["status"] == "TODO"
    assert task["priority"] == "MEDIUM"

    path = f"{URL}/{task['id']}"

    # Read
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == task

    # List
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == [task]

    # Update
    response = client.patch(path, json={"status": "DONE"})
    assert response.status_code == 200

    updated = response.json()
    assert updated["status"] == "DONE"
    assert updated["title"] == task["title"]
    assert updated["created_at"] == task["created_at"]

    # Kiểm tra thay đổi đã được lưu
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == updated

    # Delete
    response = client.delete(path)
    assert response.status_code == 204
    assert response.content == b""

    # Task đã bị xóa
    assert client.get(path).status_code == 404
    assert client.get(URL).json() == []


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_task_not_found(client: TestClient, method: str):
    kwargs = {}

    if method == "PATCH":
        kwargs["json"] = {"status": "DONE"}

    response = client.request(
        method,
        f"{URL}/99999",
        **kwargs,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

def create_task(client: TestClient, **fields) -> dict:
    response = client.post(
        URL,
        json={"title": "Task test", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("title", ["", "   ", "\t\n", "a" * 256, None])
def test_invalid_title(client: TestClient, method: str, title):
    path = URL

    if method == "PATCH":
        task = create_task(client)
        path = f"{URL}/{task['id']}"

    response = client.request(method, path, json={"title": title})
    assert response.status_code == 422


def test_create_requires_title(client: TestClient):
    response = client.post(URL, json={})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["title", "status", "priority"])
def test_patch_rejects_null(client: TestClient, field: str):
    task = create_task(client)
    path = f"{URL}/{task['id']}"

    response = client.patch(path, json={field: None})

    assert response.status_code == 422
    assert client.get(path).json() == task


@pytest.mark.parametrize("value", ["TODO", "DONE", None])
def test_create_rejects_status(client: TestClient, value):
    response = client.post(
        URL,
        json={"title": "Task test", "status": value},
    )

    assert response.status_code == 422
    assert client.get(URL).json() == []


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_reject_past_due_date(client: TestClient, method: str):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    path = URL
    payload = {"title": "Task test", "due_date": yesterday}

    if method == "PATCH":
        task = create_task(client)
        path = f"{URL}/{task['id']}"
        payload = {"due_date": yesterday}

    response = client.request(method, path, json=payload)

    assert response.status_code == 422

    if method == "PATCH":
        assert client.get(path).json() == task
    else:
        assert client.get(URL).json() == []


@pytest.mark.parametrize("days", [0, 1])
def test_accept_today_and_future(client: TestClient, days: int):
    due_date = (date.today() + timedelta(days=days)).isoformat()
    task = create_task(client, due_date=due_date)

    assert task["due_date"] == due_date

    response = client.patch(
        f"{URL}/{task['id']}",
        json={"due_date": due_date},
    )
    assert response.status_code == 200
    assert response.json()["due_date"] == due_date


def test_empty_patch_preserves_task(client: TestClient):
    task = create_task(client)

    response = client.patch(f"{URL}/{task['id']}", json={})

    assert response.status_code == 200
    assert response.json() == task


def test_patch_can_clear_nullable_fields(client: TestClient):
    task = create_task(
        client,
        description="Description",
        due_date=(date.today() + timedelta(days=1)).isoformat(),
    )
    path = f"{URL}/{task['id']}"

    response = client.patch(
        path,
        json={"description": None, "due_date": None},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["description"] is None
    assert updated["due_date"] is None
    assert updated["title"] == task["title"]
    assert client.get(path).json() == updated


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    "payload",
    [
        {"priority": "INVALID"},
        {"due_date": "not-a-date"},
    ],
)
def test_invalid_values(client: TestClient, method: str, payload: dict):
    path = URL

    if method == "POST":
        payload = {"title": "Task test", **payload}
    else:
        task = create_task(client)
        path = f"{URL}/{task['id']}"

    response = client.request(method, path, json=payload)
    assert response.status_code == 422


def test_patch_rejects_invalid_status(client: TestClient):
    task = create_task(client)

    response = client.patch(
        f"{URL}/{task['id']}",
        json={"status": "INVALID"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"skip": -1},
        {"limit": 0},
        {"limit": 101},
        {"skip": "abc"},
    ],
)
def test_invalid_pagination(client: TestClient, params: dict):
    response = client.get(URL, params=params)
    assert response.status_code == 422


def test_pagination(client: TestClient):
    tasks = [
        create_task(client, title=f"Task {i}")
        for i in range(21)
    ]

    # Limit mặc định là 20
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == tasks[:20]

    # Bỏ qua task đầu, lấy một task tiếp theo
    response = client.get(URL, params={"skip": 1, "limit": 1})
    assert response.status_code == 200
    assert response.json() == [tasks[1]]

    # Bỏ qua toàn bộ dữ liệu
    response = client.get(URL, params={"skip": 21})
    assert response.status_code == 200
    assert response.json() == []

    # Limit tối đa vẫn hợp lệ
    response = client.get(URL, params={"limit": 100})
    assert response.status_code == 200
    assert response.json() == tasks