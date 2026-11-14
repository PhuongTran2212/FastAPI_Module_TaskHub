import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.core import messages
from app.core.constants import DEFAULT_LABEL_COLOR, LABEL_NAME_MAX_LENGTH
from app.core.enums import WorkspaceRole
from app.core.security import create_access_token
from app.main import app
from app.models import Label, Project, User, Workspace, WorkspaceMember
from tests.conftest import TEST_DATABASE_URL

URL = "/api/v1/labels"


def project_labels(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/labels"


def task_labels(task_id: int, label_id: int | None = None) -> str:
    path = f"/api/v1/tasks/{task_id}/labels"
    return path if label_id is None else f"{path}/{label_id}"


async def create_label(client, project_id, headers=None, **fields) -> dict:
    response = await client.post(
        project_labels(project_id),
        json={"name": "Bug", **fields},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_task(client, project_id) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks", json={"title": "Task"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_editor_manages_labels(client, seed_data, roles):
    headers = roles["editor"]["headers"]
    project_id = seed_data["project_id"]
    bug = await create_label(
        client, project_id, headers, name="  Bug  ", color="#ff0000"
    )
    assert bug == {
        "id": bug["id"],
        "project_id": project_id,
        "name": "Bug",
        "color": "#FF0000",
    }
    feature = await create_label(client, project_id, headers, name="Feature")
    assert feature["color"] == DEFAULT_LABEL_COLOR

    response = await client.get(project_labels(project_id), headers=headers)
    assert [label["name"] for label in response.json()] == ["Bug", "Feature"]

    response = await client.patch(
        f"{URL}/{bug['id']}",
        json={"name": "Defect", "color": "#00ff00"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {**bug, "name": "Defect", "color": "#00FF00"}

    assert (
        await client.delete(f"{URL}/{bug['id']}", headers=headers)
    ).status_code == 204
    response = await client.get(project_labels(project_id), headers=headers)
    assert [label["id"] for label in response.json()] == [feature["id"]]


async def test_label_name_is_unique_per_project(client, seed_data):
    await create_label(client, seed_data["project_id"], name="Bug")
    response = await client.post(
        project_labels(seed_data["project_id"]), json={"name": "Bug"}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": messages.LABEL_NAME_EXISTS}

    other = await create_label(client, seed_data["project_id"], name="Other")
    response = await client.patch(f"{URL}/{other['id']}", json={"name": "Bug"})
    assert response.status_code == 409
    assert response.json() == {"detail": messages.LABEL_NAME_EXISTS}

    # Cùng tên ở project khác thì được
    await create_label(client, seed_data["other_project_id"], name="Bug")


@pytest.mark.parametrize(
    "method,payload",
    [
        ("POST", {}),
        ("POST", {"name": "   "}),
        ("POST", {"name": "a" * (LABEL_NAME_MAX_LENGTH + 1)}),
        ("POST", {"name": "Bug", "color": "red"}),
        ("POST", {"name": "Bug", "color": "#12345"}),
        ("POST", {"name": "Bug", "color": "#1234567"}),
        ("POST", {"name": "Bug", "color": "#GGGGGG"}),
        ("POST", {"name": "Bug", "project_id": 1}),
        ("PATCH", {"name": None}),
        ("PATCH", {"color": None}),
        ("PATCH", {"color": "blue"}),
    ],
)
async def test_label_validation(client, seed_data, method, payload):
    if method == "POST":
        url = project_labels(seed_data["project_id"])
    else:
        label = await create_label(client, seed_data["project_id"])
        url = f"{URL}/{label['id']}"
    assert (await client.request(method, url, json=payload)).status_code == 422


async def test_viewer_reads_labels_but_cannot_change_them(client, seed_data, roles):
    label = await create_label(client, seed_data["project_id"])
    task = await create_task(client, seed_data["project_id"])
    headers = roles["viewer"]["headers"]

    response = await client.get(
        project_labels(seed_data["project_id"]), headers=headers
    )
    assert response.status_code == 200
    response = await client.get(task_labels(task["id"]), headers=headers)
    assert response.status_code == 200

    for method, url, payload in (
        ("POST", project_labels(seed_data["project_id"]), {"name": "New"}),
        ("PATCH", f"{URL}/{label['id']}", {"name": "X"}),
        ("DELETE", f"{URL}/{label['id']}", None),
        ("POST", task_labels(task["id"], label["id"]), None),
        ("DELETE", task_labels(task["id"], label["id"]), None),
    ):
        response = await client.request(method, url, json=payload, headers=headers)
        assert response.status_code == 403, (method, url)


async def test_outsider_gets_404(client, seed_data, roles):
    label = await create_label(client, seed_data["project_id"])
    task = await create_task(client, seed_data["project_id"])
    headers = roles["outsider"]["headers"]

    response = await client.patch(
        f"{URL}/{label['id']}", json={"name": "X"}, headers=headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Label not found"}
    response = await client.get(
        project_labels(seed_data["project_id"]), headers=headers
    )
    assert response.json() == {"detail": "Project not found"}
    response = await client.get(task_labels(task["id"]), headers=headers)
    assert response.json() == {"detail": "Task not found"}


async def test_attach_and_detach_are_idempotent(client, seed_data, roles):
    headers = roles["editor"]["headers"]
    label = await create_label(client, seed_data["project_id"])
    task = await create_task(client, seed_data["project_id"])
    path = task_labels(task["id"], label["id"])

    for _ in range(2):
        response = await client.post(path, headers=headers)
        assert response.status_code == 204
        assert response.content == b""
    assert (await client.get(task_labels(task["id"]))).json() == [label]

    for _ in range(2):
        assert (await client.delete(path, headers=headers)).status_code == 204
    assert (await client.get(task_labels(task["id"]))).json() == []


async def test_label_must_belong_to_the_task_project(client, seed_data):
    task = await create_task(client, seed_data["project_id"])
    foreign = await create_label(client, seed_data["other_project_id"])
    for label_id in (foreign["id"], 999_999_999):
        for method in ("POST", "DELETE"):
            response = await client.request(method, task_labels(task["id"], label_id))
            assert response.status_code == 404
            assert response.json() == {"detail": "Label not found"}


async def test_deleting_a_label_detaches_it(client, seed_data):
    label = await create_label(client, seed_data["project_id"])
    task = await create_task(client, seed_data["project_id"])
    await client.post(task_labels(task["id"], label["id"]))
    assert (await client.delete(f"{URL}/{label['id']}")).status_code == 204
    assert (await client.get(task_labels(task["id"]))).json() == []


async def test_archived_project_labels_are_read_only(client, seed_data):
    label = await create_label(client, seed_data["project_id"])
    task = await create_task(client, seed_data["project_id"])
    await client.patch(
        f"/api/v1/projects/{seed_data['project_id']}", json={"status": "ARCHIVED"}
    )

    assert (
        await client.get(project_labels(seed_data["project_id"]))
    ).status_code == 200
    for method, url, payload in (
        ("POST", project_labels(seed_data["project_id"]), {"name": "New"}),
        ("PATCH", f"{URL}/{label['id']}", {"name": "X"}),
        ("DELETE", f"{URL}/{label['id']}", None),
        ("POST", task_labels(task["id"], label["id"]), None),
        ("DELETE", task_labels(task["id"], label["id"]), None),
    ):
        response = await client.request(method, url, json=payload)
        assert response.status_code == 409, (method, url)
        assert response.json() == {"detail": messages.PROJECT_ARCHIVED}


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", project_labels(1)),
        ("POST", project_labels(1)),
        ("PATCH", f"{URL}/1"),
        ("DELETE", f"{URL}/1"),
        ("GET", task_labels(1)),
        ("POST", task_labels(1, 1)),
        ("DELETE", task_labels(1, 1)),
    ],
)
async def test_label_endpoints_require_login(client, method, path):
    request = client.build_request(method, path, json={})
    request.headers.pop("Authorization", None)
    response = await client.send(request)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_label_names_are_deliberately_case_sensitive(client, seed_data):
    bug = await create_label(client, seed_data["project_id"], name="Bug")
    lowercase = await create_label(client, seed_data["project_id"], name="bug")
    assert bug["id"] != lowercase["id"]
    response = await client.get(project_labels(seed_data["project_id"]))
    assert response.status_code == 200
    assert sorted(response.json(), key=lambda item: item["id"]) == [bug, lowercase]


async def test_label_lists_return_all_items_in_name_order(client, seed_data):
    project_id = seed_data["project_id"]
    zeta = await create_label(client, project_id, name="Zeta")
    alpha = await create_label(client, project_id, name="Alpha")
    task = await create_task(client, project_id)
    for label in (zeta, alpha):
        response = await client.post(task_labels(task["id"], label["id"]))
        assert response.status_code == 204
    for path in (project_labels(project_id), task_labels(task["id"])):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json() == [alpha, zeta]


async def test_reverse_label_index_exists_in_migrated_database(db_connection):
    indexes = await db_connection.run_sync(
        lambda connection: inspect(connection).get_indexes("task_labels")
    )
    assert any(
        item["name"] == "ix_task_labels_label_id"
        and item["column_names"] == ["label_id"]
        for item in indexes
    )


@pytest_asyncio.fixture
async def concurrent_label_client(migrated_database):
    # Independent connections and real commits test unique-constraint races.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    email = f"label-race-{uuid.uuid4().hex}@example.com"
    user_id = workspace_id = None

    async def override_get_db():
        async with factory() as session:
            yield session

    previous = app.dependency_overrides.copy()
    try:
        async with factory() as session:
            async with session.begin():
                user = User(
                    email=email,
                    full_name="Label race",
                    hashed_password="TEST_LOGIN_DISABLED",
                )
                session.add(user)
                await session.flush()
                user_id = user.id
                workspace = Workspace(name="Label race", owner_id=user_id)
                session.add(workspace)
                await session.flush()
                workspace_id = workspace.id
                session.add(
                    WorkspaceMember(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role=WorkspaceRole.OWNER,
                    )
                )
                project = Project(name="Label race", workspace_id=workspace_id)
                session.add(project)
                await session.flush()
                project_id = project.id
        app.dependency_overrides[get_db] = override_get_db
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app),
                base_url="http://testserver",
                headers={"Authorization": "Bearer " + create_access_token(user_id)},
            ) as client:
                yield client, project_id, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        try:
            async with factory() as session:
                async with session.begin():
                    if workspace_id is not None:
                        await session.execute(
                            delete(Workspace).where(Workspace.id == workspace_id)
                        )
                    if user_id is not None:
                        await session.execute(delete(User).where(User.id == user_id))
        finally:
            await engine.dispose()


async def test_concurrent_label_creation_returns_201_and_409(concurrent_label_client):
    client, project_id, factory = concurrent_label_client
    responses = await asyncio.gather(
        *[
            client.post(project_labels(project_id), json={"name": "Bug"})
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json() == {"detail": messages.LABEL_NAME_EXISTS}
    winner = next(
        response.json() for response in responses if response.status_code == 201
    )
    async with factory() as session:
        labels = (
            await session.scalars(select(Label).where(Label.project_id == project_id))
        ).all()
        assert len(labels) == 1
        assert labels[0].id == winner["id"]
    await create_label(client, project_id, name="Other")
