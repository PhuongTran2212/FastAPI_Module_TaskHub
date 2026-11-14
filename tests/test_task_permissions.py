"""RBAC cho task: ADMIN / OWNER / EDITOR / VIEWER và người ngoài workspace."""

import pytest

from app.core import messages

URL = "/api/v1/tasks"


def project_tasks(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/tasks"


async def create_task(client, seed_data, headers=None, **fields) -> dict:
    response = await client.post(
        project_tasks(seed_data["project_id"]),
        json={"title": "Task", **fields},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", project_tasks(1), None),
        ("POST", project_tasks(1), {"title": "Task"}),
        ("GET", f"{URL}/1", None),
        ("PATCH", f"{URL}/1", {"title": "Changed"}),
        ("DELETE", f"{URL}/1", None),
    ],
)
async def test_all_task_endpoints_require_login(client, method, path, payload):
    request = client.build_request(method, path, json=payload)
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_creator_comes_from_current_user(client, seed_data, roles):
    editor = roles["editor"]
    task = await create_task(client, seed_data, headers=editor["headers"])
    assert task["created_by"] == editor["id"]


async def test_viewer_can_read_but_not_write(client, seed_data, roles):
    task = await create_task(client, seed_data)
    headers = roles["viewer"]["headers"]
    path = f"{URL}/{task['id']}"

    assert (await client.get(path, headers=headers)).json() == task
    response = await client.get(project_tasks(seed_data["project_id"]), headers=headers)
    assert response.json()["total"] == 1

    for method, url, payload in (
        ("POST", project_tasks(seed_data["project_id"]), {"title": "New"}),
        ("PATCH", path, {"status": "DONE"}),
        ("DELETE", path, None),
    ):
        response = await client.request(method, url, json=payload, headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": messages.PERMISSION_DENIED}


async def test_editor_updates_any_task_but_deletes_only_own(client, seed_data, roles):
    headers = roles["editor"]["headers"]
    owners_task = await create_task(client, seed_data)
    own_task = await create_task(client, seed_data, headers=headers)

    response = await client.patch(
        f"{URL}/{owners_task['id']}",
        json={"status": "IN_PROGRESS", "priority": "URGENT"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"

    response = await client.delete(f"{URL}/{owners_task['id']}", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": messages.TASK_DELETE_NOT_ALLOWED}
    assert (await client.get(f"{URL}/{owners_task['id']}")).status_code == 200

    response = await client.delete(f"{URL}/{own_task['id']}", headers=headers)
    assert response.status_code == 204


async def test_owner_and_admin_delete_any_task(client, seed_data, roles):
    editors_task = await create_task(
        client, seed_data, headers=roles["editor"]["headers"]
    )
    assert (await client.delete(f"{URL}/{editors_task['id']}")).status_code == 204

    another = await create_task(client, seed_data, headers=roles["editor"]["headers"])
    response = await client.delete(
        f"{URL}/{another['id']}", headers=roles["admin"]["headers"]
    )
    assert response.status_code == 204


async def test_admin_works_without_membership(client, seed_data, roles):
    headers = roles["admin"]["headers"]
    task = await create_task(client, seed_data, headers=headers)
    assert task["created_by"] == roles["admin"]["id"]
    response = await client.patch(
        f"{URL}/{task['id']}", json={"status": "DONE"}, headers=headers
    )
    assert response.status_code == 200


async def test_outsider_cannot_see_tasks(client, seed_data, roles):
    task = await create_task(client, seed_data)
    headers = roles["outsider"]["headers"]
    for method in ("GET", "PATCH", "DELETE"):
        kwargs = {"json": {"title": "X"}} if method == "PATCH" else {}
        response = await client.request(
            method, f"{URL}/{task['id']}", headers=headers, **kwargs
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Task not found"}
    response = await client.get(project_tasks(seed_data["project_id"]), headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.parametrize(
    "assignee,allowed",
    [("editor", True), ("viewer", False), ("outsider", False), ("admin", False)],
)
async def test_assignee_must_be_owner_or_editor_member(
    client, seed_data, roles, assignee, allowed
):
    assignee_id = roles[assignee]["id"]
    response = await client.post(
        project_tasks(seed_data["project_id"]),
        json={"title": "Task", "assignee_id": assignee_id},
    )
    task = await create_task(client, seed_data)
    patched = await client.patch(
        f"{URL}/{task['id']}", json={"assignee_id": assignee_id}
    )
    if allowed:
        assert response.status_code == 201
        assert response.json()["assignee_id"] == assignee_id
        assert patched.status_code == 200
    else:
        for result in (response, patched):
            assert result.status_code == 422
            assert result.json() == {"detail": messages.ASSIGNEE_NOT_ALLOWED}


async def test_archived_project_tasks_are_read_only(client, seed_data):
    task = await create_task(client, seed_data)
    project_path = f"/api/v1/projects/{seed_data['project_id']}"
    await client.patch(project_path, json={"status": "ARCHIVED"})

    assert (await client.get(f"{URL}/{task['id']}")).status_code == 200
    for method, url, payload in (
        ("POST", project_tasks(seed_data["project_id"]), {"title": "New"}),
        ("PATCH", f"{URL}/{task['id']}", {"status": "DONE"}),
        ("DELETE", f"{URL}/{task['id']}", None),
    ):
        response = await client.request(method, url, json=payload)
        assert response.status_code == 409
        assert response.json() == {"detail": messages.PROJECT_ARCHIVED}

    await client.patch(project_path, json={"status": "ACTIVE"})
    assert (
        await client.patch(f"{URL}/{task['id']}", json={"status": "DONE"})
    ).status_code == 200
