import pytest

from tests.auth_helpers import bearer, login, register


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/v1/tasks", None),
        ("POST", "/api/v1/tasks", {"title": "Task", "project_id": 1}),
        ("GET", "/api/v1/tasks/1", None),
        ("PATCH", "/api/v1/tasks/1", {"title": "Changed"}),
        ("DELETE", "/api/v1/tasks/1", None),
    ],
)
async def test_all_task_endpoints_require_login(client, method, path, payload):
    request = client.build_request(method, path, json=payload)
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_task_creator_comes_from_current_user(client, seed_data):
    user = await register(client)
    tokens = await login(client)
    payload = {"title": "Task", "project_id": seed_data["project_id"]}
    response = await client.post(
        "/api/v1/tasks", headers=bearer(tokens["access_token"]), json=payload
    )
    assert response.status_code == 201
    assert response.json()["created_by"] == user["id"]
    response = await client.post(
        "/api/v1/tasks", json={**payload, "created_by": user["id"]}
    )
    assert response.status_code == 422


async def test_day3_authenticated_non_owner_can_edit_until_day4(client, seed_data):
    response = await client.post(
        "/api/v1/tasks", json={"title": "Owned", "project_id": seed_data["project_id"]}
    )
    task = response.json()
    other = await register(client)
    tokens = await login(client)
    assert other["id"] != task["created_by"]
    headers = bearer(tokens["access_token"])
    assert (
        await client.patch(
            f"/api/v1/tasks/{task['id']}", headers=headers, json={"title": "Edited"}
        )
    ).status_code == 200
    assert (
        await client.delete(f"/api/v1/tasks/{task['id']}", headers=headers)
    ).status_code == 204
