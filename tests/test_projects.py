import pytest

from app.core import messages
from app.core.constants import PROJECT_NAME_MAX_LENGTH
from app.models import Project, Task

URL = "/api/v1/projects"
MISSING_ID = 999_999_999


def projects_url(workspace_id: int) -> str:
    return f"/api/v1/workspaces/{workspace_id}/projects"


async def test_editor_creates_and_updates_project(client, seed_data, roles):
    headers = roles["editor"]["headers"]
    response = await client.post(
        projects_url(seed_data["workspace_id"]),
        json={"name": "  Website  ", "description": "Redesign"},
        headers=headers,
    )
    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "Website"
    assert project["workspace_id"] == seed_data["workspace_id"]
    assert project["status"] == "ACTIVE"

    path = f"{URL}/{project['id']}"
    assert (await client.get(path, headers=headers)).json() == project
    response = await client.patch(
        path, json={"name": "Website v2", "description": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {**project, "name": "Website v2", "description": None}


async def test_viewer_reads_but_cannot_write(client, seed_data, roles):
    headers = roles["viewer"]["headers"]
    path = f"{URL}/{seed_data['project_id']}"
    assert (await client.get(path, headers=headers)).status_code == 200
    response = await client.get(
        projects_url(seed_data["workspace_id"]), headers=headers
    )
    assert response.status_code == 200

    requests = [
        ("POST", projects_url(seed_data["workspace_id"]), {"name": "New"}),
        ("PATCH", path, {"name": "Renamed"}),
        ("DELETE", path, None),
    ]
    for method, url, payload in requests:
        response = await client.request(method, url, json=payload, headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": messages.PERMISSION_DENIED}


async def test_outsider_gets_404(client, seed_data, roles):
    headers = roles["outsider"]["headers"]
    for project_id in (seed_data["project_id"], MISSING_ID):
        response = await client.get(f"{URL}/{project_id}", headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Project not found"}
    response = await client.post(
        projects_url(seed_data["workspace_id"]), json={"name": "X"}, headers=headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


async def test_list_projects_with_pagination_and_status(client, seed_data):
    url = projects_url(seed_data["workspace_id"])
    response = await client.get(url, params={"limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [seed_data["project_id"]]

    await client.patch(
        f"{URL}/{seed_data['other_project_id']}", json={"status": "ARCHIVED"}
    )
    archived = (await client.get(url, params={"status": "ARCHIVED"})).json()
    assert [item["id"] for item in archived["items"]] == [seed_data["other_project_id"]]
    assert (await client.get(url, params={"status": "ACTIVE"})).json()["total"] == 1
    assert (await client.get(url, params={"status": "OTHER"})).status_code == 422


async def test_archive_and_restore(client, seed_data, roles):
    path = f"{URL}/{seed_data['project_id']}"
    headers = roles["editor"]["headers"]
    response = await client.patch(path, json={"status": "ARCHIVED"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"
    response = await client.patch(path, json={"status": "ACTIVE"}, headers=headers)
    assert response.json()["status"] == "ACTIVE"


@pytest.mark.parametrize(
    "method,payload",
    [
        ("POST", {}),
        ("POST", {"name": "   "}),
        ("POST", {"name": "a" * (PROJECT_NAME_MAX_LENGTH + 1)}),
        ("POST", {"name": "X", "workspace_id": 1}),
        ("POST", {"name": "X", "status": "ARCHIVED"}),
        ("PATCH", {"name": None}),
        ("PATCH", {"status": None}),
        ("PATCH", {"status": "DELETED"}),
        ("PATCH", {"workspace_id": 1}),
    ],
)
async def test_project_validation(client, seed_data, method, payload):
    url = (
        projects_url(seed_data["workspace_id"])
        if method == "POST"
        else f"{URL}/{seed_data['project_id']}"
    )
    assert (await client.request(method, url, json=payload)).status_code == 422


async def test_only_owner_deletes_project_and_its_tasks(
    client, seed_data, roles, session_factory
):
    async with session_factory() as session:
        async with session.begin():
            task = Task(
                title="T",
                project_id=seed_data["project_id"],
                created_by=seed_data["creator_id"],
            )
            session.add(task)
            await session.flush()
            task_id = task.id

    path = f"{URL}/{seed_data['project_id']}"
    response = await client.delete(path, headers=roles["editor"]["headers"])
    assert response.status_code == 403
    assert (await client.delete(path)).status_code == 204
    assert (await client.get(path)).status_code == 404
    async with session_factory() as session:
        assert await session.get(Project, seed_data["project_id"]) is None
        assert await session.get(Task, task_id) is None


async def test_admin_manages_projects_without_membership(client, seed_data, roles):
    headers = roles["admin"]["headers"]
    response = await client.post(
        projects_url(seed_data["workspace_id"]), json={"name": "Admin"}, headers=headers
    )
    assert response.status_code == 201
    path = f"{URL}/{response.json()['id']}"
    assert (await client.delete(path, headers=headers)).status_code == 204


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/workspaces/1/projects"),
        ("POST", "/api/v1/workspaces/1/projects"),
        ("GET", f"{URL}/1"),
        ("PATCH", f"{URL}/1"),
        ("DELETE", f"{URL}/1"),
    ],
)
async def test_project_endpoints_require_login(client, method, path):
    request = client.build_request(method, path, json={})
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
