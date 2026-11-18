import pytest

from app.core import messages
from app.core.constants import COMMENT_CONTENT_MAX_LENGTH
from app.models import Comment

URL = "/api/v1/comments"


def task_comments(task_id: int) -> str:
    return f"/api/v1/tasks/{task_id}/comments"


async def create_task(client, seed_data) -> dict:
    response = await client.post(
        f"/api/v1/projects/{seed_data['project_id']}/tasks", json={"title": "Task"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_comment(client, task_id, content="Looks good", headers=None) -> dict:
    response = await client.post(
        task_comments(task_id), json={"content": content}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_members_add_and_list_comments(client, seed_data, roles):
    task = await create_task(client, seed_data)
    first = await add_comment(client, task["id"], "  First  ")
    assert first["content"] == "First"
    assert first["task_id"] == task["id"]
    assert first["author_id"] == seed_data["creator_id"]
    assert first["created_at"]
    second = await add_comment(
        client, task["id"], "Second", headers=roles["editor"]["headers"]
    )
    assert second["author_id"] == roles["editor"]["id"]

    # VIEWER đọc được, theo thứ tự cũ → mới, có phân trang
    response = await client.get(
        task_comments(task["id"]),
        params={"limit": 1, "page": 2},
        headers=roles["viewer"]["headers"],
    )
    assert response.status_code == 200
    assert response.json() == {"items": [second], "total": 2, "page": 2, "limit": 1}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": ""},
        {"content": "   "},
        {"content": "a" * (COMMENT_CONTENT_MAX_LENGTH + 1)},
        {"content": "Hi", "author_id": 1},
        {"content": "Hi", "task_id": 1},
    ],
)
async def test_comment_validation(client, seed_data, payload):
    task = await create_task(client, seed_data)
    response = await client.post(task_comments(task["id"]), json=payload)
    assert response.status_code == 422


async def test_viewer_cannot_add_or_delete(client, seed_data, roles):
    task = await create_task(client, seed_data)
    comment = await add_comment(client, task["id"])
    headers = roles["viewer"]["headers"]
    response = await client.post(
        task_comments(task["id"]), json={"content": "Hi"}, headers=headers
    )
    assert response.status_code == 403
    response = await client.delete(f"{URL}/{comment['id']}", headers=headers)
    assert response.status_code == 403


async def test_only_author_or_owner_deletes_a_comment(client, seed_data, roles):
    task = await create_task(client, seed_data)
    editor = roles["editor"]["headers"]
    owners_comment = await add_comment(client, task["id"])
    editors_comment = await add_comment(client, task["id"], headers=editor)

    response = await client.delete(f"{URL}/{owners_comment['id']}", headers=editor)
    assert response.status_code == 403
    assert response.json() == {"detail": messages.COMMENT_DELETE_NOT_ALLOWED}

    response = await client.delete(f"{URL}/{editors_comment['id']}", headers=editor)
    assert response.status_code == 204
    assert response.content == b""

    another = await add_comment(client, task["id"], headers=editor)
    assert (await client.delete(f"{URL}/{another['id']}")).status_code == 204
    last = await add_comment(client, task["id"], headers=editor)
    response = await client.delete(
        f"{URL}/{last['id']}", headers=roles["admin"]["headers"]
    )
    assert response.status_code == 204

    remaining = (await client.get(task_comments(task["id"]))).json()
    assert [item["id"] for item in remaining["items"]] == [owners_comment["id"]]
    response = await client.delete(f"{URL}/{editors_comment['id']}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Comment not found"}


async def test_outsider_gets_404(client, seed_data, roles):
    task = await create_task(client, seed_data)
    comment = await add_comment(client, task["id"])
    headers = roles["outsider"]["headers"]
    for method, url, payload, resource in (
        ("GET", task_comments(task["id"]), None, "Task"),
        ("POST", task_comments(task["id"]), {"content": "Hi"}, "Task"),
        ("DELETE", f"{URL}/{comment['id']}", None, "Comment"),
    ):
        response = await client.request(method, url, json=payload, headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": f"{resource} not found"}


async def test_archived_project_comments_are_read_only(client, seed_data):
    task = await create_task(client, seed_data)
    comment = await add_comment(client, task["id"])
    await client.patch(
        f"/api/v1/projects/{seed_data['project_id']}", json={"status": "ARCHIVED"}
    )
    assert (await client.get(task_comments(task["id"]))).json()["total"] == 1
    for method, url, payload in (
        ("POST", task_comments(task["id"]), {"content": "Hi"}),
        ("DELETE", f"{URL}/{comment['id']}", None),
    ):
        response = await client.request(method, url, json=payload)
        assert response.status_code == 409
        assert response.json() == {"detail": messages.PROJECT_ARCHIVED}


async def test_deleting_a_task_deletes_its_comments(client, seed_data, session_factory):
    task = await create_task(client, seed_data)
    comment = await add_comment(client, task["id"])
    assert (await client.delete(f"/api/v1/tasks/{task['id']}")).status_code == 204
    async with session_factory() as session:
        assert await session.get(Comment, comment["id"]) is None


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", task_comments(1)),
        ("POST", task_comments(1)),
        ("DELETE", f"{URL}/1"),
    ],
)
async def test_comment_endpoints_require_login(client, method, path):
    request = client.build_request(method, path, json={})
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
