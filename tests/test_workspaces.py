import pytest
from sqlalchemy import select

from app.core import messages
from app.core.constants import WORKSPACE_NAME_MAX_LENGTH
from app.core.enums import UserRole
from app.models import Project, Task, Workspace

URL = "/api/v1/workspaces"
MISSING_ID = 999_999_999


async def invite(client, workspace_id, email, role=None, headers=None) -> dict:
    payload = {"email": email} if role is None else {"email": email, "role": role}
    response = await client.post(
        f"{URL}/{workspace_id}/members", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_workspace_makes_creator_owner(client, seed_data):
    response = await client.post(URL, json={"name": "  Team  "})
    assert response.status_code == 201
    workspace = response.json()
    assert workspace["name"] == "Team"
    assert workspace["owner_id"] == seed_data["creator_id"]

    response = await client.get(f"{URL}/{workspace['id']}/members")
    assert response.json() == [
        {
            "user_id": seed_data["creator_id"],
            "email": "creator@example.test",
            "full_name": "Creator",
            "role": "OWNER",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "   "},
        {"name": "a" * (WORKSPACE_NAME_MAX_LENGTH + 1)},
        {"name": "Team", "owner_id": 1},
    ],
)
async def test_create_workspace_validation(client, payload):
    assert (await client.post(URL, json=payload)).status_code == 422


async def test_list_returns_only_my_workspaces(client, make_user):
    await client.post(URL, json={"name": "Second"})
    outsider = await make_user()
    await client.post(URL, json={"name": "Outsider"}, headers=outsider["headers"])

    mine = (await client.get(URL, params={"limit": 1})).json()
    assert mine["total"] == 2
    assert len(mine["items"]) == 1

    theirs = (await client.get(URL, headers=outsider["headers"])).json()
    assert [item["name"] for item in theirs["items"]] == ["Outsider"]

    admin = await make_user(UserRole.ADMIN)
    assert (await client.get(URL, headers=admin["headers"])).json()["total"] == 3


async def test_outsider_cannot_tell_if_workspace_exists(client, seed_data, make_user):
    outsider = await make_user()
    for workspace_id in (seed_data["workspace_id"], MISSING_ID):
        for path in (f"{URL}/{workspace_id}", f"{URL}/{workspace_id}/members"):
            response = await client.get(path, headers=outsider["headers"])
            assert response.status_code == 404
            assert response.json() == {"detail": "Workspace not found"}


async def test_only_owner_can_rename_or_delete(client, seed_data, make_user):
    path = f"{URL}/{seed_data['workspace_id']}"
    viewer = await make_user()
    editor = await make_user()
    await invite(client, seed_data["workspace_id"], viewer["email"], "VIEWER")
    await invite(client, seed_data["workspace_id"], editor["email"], "EDITOR")

    for member in (viewer, editor):
        headers = member["headers"]
        assert (await client.get(path, headers=headers)).status_code == 200
        response = await client.patch(path, json={"name": "X"}, headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": messages.PERMISSION_DENIED}
        assert (await client.delete(path, headers=headers)).status_code == 403

    response = await client.patch(path, json={"name": "Renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert (await client.patch(path, json={"name": None})).status_code == 422

    assert (await client.delete(path)).status_code == 204
    assert (await client.get(path)).status_code == 404


async def test_delete_workspace_cascades_to_projects(
    client, seed_data, session_factory
):
    response = await client.delete(f"{URL}/{seed_data['workspace_id']}")
    assert response.status_code == 204
    async with session_factory() as session:
        assert await session.get(Workspace, seed_data["workspace_id"]) is None
        assert await session.get(Project, seed_data["project_id"]) is None


async def test_admin_can_manage_any_workspace(client, seed_data, make_user):
    admin = await make_user(UserRole.ADMIN)
    path = f"{URL}/{seed_data['workspace_id']}"
    headers = admin["headers"]
    assert (await client.get(path, headers=headers)).status_code == 200
    response = await client.patch(path, json={"name": "By admin"}, headers=headers)
    assert response.status_code == 200
    other = await make_user()
    await invite(client, seed_data["workspace_id"], other["email"], headers=headers)


async def test_invite_member(client, seed_data, make_user):
    workspace_id = seed_data["workspace_id"]
    editor = await make_user()
    member = await invite(
        client, workspace_id, f"  {editor['email'].upper()}  ", "EDITOR"
    )
    assert member["user_id"] == editor["id"]
    assert member["email"] == editor["email"]
    assert member["role"] == "EDITOR"

    viewer = await make_user()
    assert (await invite(client, workspace_id, viewer["email"]))["role"] == "VIEWER"

    response = await client.post(
        f"{URL}/{workspace_id}/members", json={"email": editor["email"]}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": messages.MEMBER_ALREADY_EXISTS}

    response = await client.post(
        f"{URL}/{workspace_id}/members", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}

    another = await make_user()
    response = await client.post(
        f"{URL}/{workspace_id}/members",
        json={"email": another["email"], "role": "OWNER"},
    )
    assert response.status_code == 422

    # Chỉ OWNER được mời; EDITOR/VIEWER vẫn xem được danh sách member
    for member in (editor, viewer):
        response = await client.post(
            f"{URL}/{workspace_id}/members",
            json={"email": another["email"]},
            headers=member["headers"],
        )
        assert response.status_code == 403
        response = await client.get(
            f"{URL}/{workspace_id}/members", headers=member["headers"]
        )
        assert response.status_code == 200
        assert [item["role"] for item in response.json()] == [
            "OWNER",
            "EDITOR",
            "EDITOR",
            "VIEWER",
        ]


async def test_change_member_role(client, seed_data, make_user):
    workspace_id = seed_data["workspace_id"]
    member = await make_user()
    await invite(client, workspace_id, member["email"], "EDITOR")
    path = f"{URL}/{workspace_id}/members/{member['id']}"

    response = await client.patch(path, json={"role": "VIEWER"})
    assert response.status_code == 200
    assert response.json()["role"] == "VIEWER"
    assert (await client.patch(path, json={"role": "OWNER"})).status_code == 422
    assert (
        await client.patch(path, json={"role": "EDITOR"}, headers=member["headers"])
    ).status_code == 403

    response = await client.patch(
        f"{URL}/{workspace_id}/members/{seed_data['creator_id']}",
        json={"role": "VIEWER"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": messages.OWNER_MEMBERSHIP_LOCKED}

    response = await client.patch(
        f"{URL}/{workspace_id}/members/{MISSING_ID}", json={"role": "VIEWER"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Member not found"}


async def test_remove_member_unassigns_only_their_tasks_in_that_workspace(
    client, seed_data, session_factory
):
    assignee_id = seed_data["assignee_id"]
    async with session_factory() as session:
        async with session.begin():
            other_workspace = Workspace(name="Other", owner_id=seed_data["creator_id"])
            session.add(other_workspace)
            await session.flush()
            other_project = Project(name="Other", workspace_id=other_workspace.id)
            session.add(other_project)
            await session.flush()
            here = Task(
                title="Here",
                project_id=seed_data["project_id"],
                created_by=seed_data["creator_id"],
                assignee_id=assignee_id,
            )
            elsewhere = Task(
                title="Elsewhere",
                project_id=other_project.id,
                created_by=seed_data["creator_id"],
                assignee_id=assignee_id,
            )
            session.add_all([here, elsewhere])
            await session.flush()
            task_ids = (here.id, elsewhere.id)

    path = f"{URL}/{seed_data['workspace_id']}/members/{assignee_id}"
    assert (await client.delete(path)).status_code == 204

    async with session_factory() as session:
        assignees = (
            await session.scalars(
                select(Task.assignee_id).where(Task.id.in_(task_ids)).order_by(Task.id)
            )
        ).all()
    assert assignees == [None, assignee_id]

    members = (await client.get(f"{URL}/{seed_data['workspace_id']}/members")).json()
    assert assignee_id not in [member["user_id"] for member in members]
    response = await client.delete(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Member not found"}


async def test_owner_cannot_be_removed_and_removed_member_loses_access(
    client, seed_data, make_user
):
    workspace_id = seed_data["workspace_id"]
    response = await client.delete(
        f"{URL}/{workspace_id}/members/{seed_data['creator_id']}"
    )
    assert response.status_code == 409

    member = await make_user()
    await invite(client, workspace_id, member["email"], "EDITOR")
    response = await client.delete(
        f"{URL}/{workspace_id}/members/{seed_data['assignee_id']}",
        headers=member["headers"],
    )
    assert response.status_code == 403

    assert (
        await client.get(f"{URL}/{workspace_id}", headers=member["headers"])
    ).status_code == 200
    assert (
        await client.delete(f"{URL}/{workspace_id}/members/{member['id']}")
    ).status_code == 204
    assert (
        await client.get(f"{URL}/{workspace_id}", headers=member["headers"])
    ).status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", URL),
        ("POST", URL),
        ("GET", f"{URL}/1"),
        ("PATCH", f"{URL}/1"),
        ("DELETE", f"{URL}/1"),
        ("GET", f"{URL}/1/members"),
        ("POST", f"{URL}/1/members"),
        ("PATCH", f"{URL}/1/members/1"),
        ("DELETE", f"{URL}/1/members/1"),
    ],
)
async def test_workspace_endpoints_require_login(client, method, path):
    request = client.build_request(method, path, json={})
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
