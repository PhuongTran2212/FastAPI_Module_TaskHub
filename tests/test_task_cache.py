import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db, get_task_cache
from app.core.enums import UserRole
from app.core.security import create_access_token
from app.main import app
from app.models import Project, User, Workspace
from app.repositories.task_repository import TaskRepository
from tests.conftest import TEST_DATABASE_URL
from tests.test_tasks import create_task, project_tasks


@pytest.fixture
def caching(client, task_page_cache, monkeypatch):
    """Real PostgreSQL/API requests, with an isolated Redis namespace per test."""
    app.dependency_overrides[get_task_cache] = lambda: task_page_cache
    original = TaskRepository.list_filtered
    loads = []

    async def counted(repository, **filters):
        loads.append(filters)
        return await original(repository, **filters)

    monkeypatch.setattr(TaskRepository, "list_filtered", counted)
    return task_page_cache, loads


async def version(session_factory, project_id):
    async with session_factory() as session:
        return await session.scalar(
            select(Project.task_cache_version).where(Project.id == project_id)
        )


async def test_cache_hit_skips_task_query_and_keeps_response_contract(
    client, seed_data, caching
):
    cache, loads = caching
    task = await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    first = await client.get(path)
    second = await client.get(path)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert second.json()["items"] == [task]
    assert len(loads) == 1
    keys = [key async for key in cache.client.scan_iter(match=f"{cache.namespace}:*")]
    assert len(keys) == 1
    assert 0 < await cache.client.ttl(keys[0]) <= cache.ttl_seconds


async def test_cache_separates_projects_pages_limits_and_every_filter(
    client, seed_data, caching
):
    _, loads = caching
    first = await create_task(client, seed_data, assignee_id=seed_data["assignee_id"])
    second = await create_task(client, seed_data, priority="HIGH")
    response = await client.patch(
        f"/api/v1/tasks/{second['id']}", json={"status": "DONE"}
    )
    assert response.status_code == 200
    second = response.json()
    other = await create_task(
        client, seed_data, project_id=seed_data["other_project_id"]
    )
    cases = [
        (seed_data["project_id"], {}, [first, second], 2),
        (seed_data["project_id"], {"page": 2, "limit": 1}, [second], 2),
        (seed_data["project_id"], {"limit": 1}, [first], 2),
        (seed_data["project_id"], {"status": "DONE"}, [second], 1),
        (seed_data["project_id"], {"priority": "HIGH"}, [second], 1),
        (
            seed_data["project_id"],
            {"assignee_id": seed_data["assignee_id"]},
            [first],
            1,
        ),
        (seed_data["project_id"], {"status": "DONE", "priority": "HIGH"}, [second], 1),
        (seed_data["project_id"], {"status": "IN_REVIEW"}, [], 0),
        (seed_data["other_project_id"], {}, [other], 1),
    ]
    for project_id, params, items, total in cases:
        for _ in range(2):
            response = await client.get(project_tasks(project_id), params=params)
            assert response.status_code == 200
            assert response.json()["items"] == items
            assert response.json()["total"] == total
    assert len(loads) == len(cases)


async def test_create_and_delete_invalidate_empty_and_nonempty_pages(
    client, seed_data, caching
):
    _, loads = caching
    path = project_tasks(seed_data["project_id"])
    assert (await client.get(path)).json()["total"] == 0
    task = await create_task(client, seed_data)
    assert (await client.get(path)).json()["items"] == [task]
    assert (await client.delete(f"/api/v1/tasks/{task['id']}")).status_code == 204
    assert (await client.get(path)).json()["total"] == 0
    assert (await client.get(path)).json()["total"] == 0
    assert len(loads) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Changed"},
        {"description": "New description"},
        {"status": "DONE"},
        {"priority": "URGENT"},
        {"due_date": (date.today() + timedelta(days=1)).isoformat()},
        {"assignee_id": "seed"},
    ],
)
async def test_patch_invalidates_all_task_fields(client, seed_data, caching, changes):
    _, loads = caching
    task = await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    assert (await client.get(path)).json()["items"] == [task]
    if changes.get("assignee_id") == "seed":
        changes = {"assignee_id": seed_data["assignee_id"]}
    response = await client.patch(f"/api/v1/tasks/{task['id']}", json=changes)
    assert response.status_code == 200
    for _ in range(2):
        assert (await client.get(path)).json()["items"] == [response.json()]
    assert len(loads) == 2


async def test_update_invalidates_filtered_totals_and_all_pages(
    client, seed_data, caching
):
    _, loads = caching
    task = await create_task(client, seed_data)
    await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    queries = [{"status": "DONE"}, {"page": 1, "limit": 1}, {"page": 2, "limit": 1}]
    for params in queries:
        assert (await client.get(path, params=params)).status_code == 200
    assert (
        await client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "DONE"})
    ).status_code == 200
    assert (await client.get(path, params=queries[0])).json()["total"] == 1
    assert (await client.delete(f"/api/v1/tasks/{task['id']}")).status_code == 204
    assert (await client.get(path, params=queries[2])).json()["items"] == []
    assert len(loads) == 5


async def test_unassign_on_member_removal_invalidates_every_affected_project(
    client, seed_data, caching
):
    _, loads = caching
    projects = (seed_data["project_id"], seed_data["other_project_id"])
    for project_id in projects:
        await create_task(
            client,
            seed_data,
            project_id=project_id,
            assignee_id=seed_data["assignee_id"],
        )
        response = await client.get(
            project_tasks(project_id), params={"assignee_id": seed_data["assignee_id"]}
        )
        assert response.json()["total"] == 1
    response = await client.delete(
        f"/api/v1/workspaces/{seed_data['workspace_id']}/members/{seed_data['assignee_id']}"
    )
    assert response.status_code == 204
    for project_id in projects:
        response = await client.get(
            project_tasks(project_id), params={"assignee_id": seed_data["assignee_id"]}
        )
        assert response.json()["total"] == 0
        response = await client.get(project_tasks(project_id))
        assert response.json()["items"][0]["assignee_id"] is None
    assert len(loads) == 6


async def test_warm_cache_does_not_bypass_current_membership(
    client, seed_data, roles, caching, monkeypatch
):
    cache, loads = caching
    await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    await client.get(path)
    get = AsyncMock(wraps=cache.get)
    monkeypatch.setattr(cache, "get", get)
    viewer = roles["viewer"]
    assert (await client.get(path, headers=viewer["headers"])).status_code == 200
    assert len(loads) == 1
    assert (
        await client.get(path, headers=roles["outsider"]["headers"])
    ).status_code == 404
    assert get.await_count == 1
    request = client.build_request("GET", path)
    request.headers.pop("Authorization", None)
    assert (await client.send(request)).status_code == 401
    assert get.await_count == 1
    response = await client.delete(
        f"/api/v1/workspaces/{seed_data['workspace_id']}/members/{viewer['id']}"
    )
    assert response.status_code == 204
    assert (await client.get(path, headers=viewer["headers"])).status_code == 404
    assert get.await_count == 1


@pytest.mark.parametrize("resource", ["projects", "workspaces"])
async def test_cascade_delete_cannot_serve_warm_tasks(
    client, seed_data, caching, resource
):
    await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    assert (await client.get(path)).json()["total"] == 1
    resource_id = (
        seed_data["project_id"] if resource == "projects" else seed_data["workspace_id"]
    )
    assert (await client.delete(f"/api/v1/{resource}/{resource_id}")).status_code == 204
    assert (await client.get(path)).status_code == 404


@pytest.mark.parametrize("operation", ["get", "set"])
async def test_redis_errors_fall_back_without_failing_api(
    client, seed_data, caching, monkeypatch, operation
):
    cache, loads = caching
    task = await create_task(client, seed_data)
    monkeypatch.setattr(
        cache.client,
        operation,
        AsyncMock(side_effect=RedisConnectionError("unavailable")),
    )
    path = project_tasks(seed_data["project_id"])
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json()["items"] == [task]
    assert len(loads) == 1


async def test_write_during_redis_outage_cannot_revive_stale_cache(
    client, seed_data, caching, monkeypatch
):
    cache, _ = caching
    task = await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    await client.get(path)
    with monkeypatch.context() as patch:
        patch.setattr(
            cache.client, "get", AsyncMock(side_effect=RedisConnectionError())
        )
        patch.setattr(
            cache.client, "set", AsyncMock(side_effect=RedisConnectionError())
        )
        updated = await client.patch(
            f"/api/v1/tasks/{task['id']}", json={"title": "During outage"}
        )
        assert updated.status_code == 200
        assert (await client.get(path)).json()["items"] == [updated.json()]
    assert (await client.get(path)).json()["items"] == [updated.json()]


async def test_failed_write_rolls_back_cache_version_and_reuses_valid_page(
    client,
    seed_data,
    caching,
    session_factory,
    monkeypatch,
):
    _, loads = caching
    task = await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    await client.get(path)
    old_version = await version(session_factory, seed_data["project_id"])
    original = TaskRepository.update

    async def fail_after_version_bump(repository, item, values):
        updated = await original(repository, item, values)
        # Real FK violation after the task and generation were changed.
        await repository.session.execute(
            text("INSERT INTO task_labels (task_id, label_id) VALUES (:id, -1)"),
            {"id": updated.id},
        )
        return updated

    monkeypatch.setattr(TaskRepository, "update", fail_after_version_bump)
    response = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"title": "Roll back"}
    )
    assert response.status_code == 409
    assert await version(session_factory, seed_data["project_id"]) == old_version
    assert (await client.get(path)).json()["items"] == [task]
    assert len(loads) == 1


async def test_late_cache_fill_cannot_resurrect_old_generation(
    client, seed_data, caching, monkeypatch
):
    cache, loads = caching
    task = await create_task(client, seed_data)
    path = project_tasks(seed_data["project_id"])
    read_finished, resume = asyncio.Event(), asyncio.Event()
    original = cache.put
    first = True

    async def delayed_put(key, page):
        nonlocal first
        if first:
            first = False
            read_finished.set()
            await asyncio.wait_for(resume.wait(), timeout=5)
        await original(key, page)

    monkeypatch.setattr(cache, "put", delayed_put)
    pending = asyncio.create_task(client.get(path))
    try:
        await asyncio.wait_for(read_finished.wait(), timeout=5)
        response = await client.patch(
            f"/api/v1/tasks/{task['id']}", json={"title": "New generation"}
        )
        assert response.status_code == 200
        assert (await client.get(path)).json()["items"] == [response.json()]
    finally:
        resume.set()
        old = await pending
    assert old.json()["items"] == [task]
    assert (await client.get(path)).json()["items"] == [response.json()]
    assert len(loads) == 2


@pytest_asyncio.fixture
async def committed_cache_client(migrated_database, task_page_cache):
    """Use independent real transactions to verify concurrent version increments."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = workspace_id = None
    previous = app.dependency_overrides.copy()

    async def override_get_db():
        async with factory() as session:
            yield session

    try:
        async with factory() as session:
            async with session.begin():
                user = User(
                    email=f"cache-race-{uuid.uuid4().hex}@example.com",
                    full_name="Cache race",
                    hashed_password="TEST_LOGIN_DISABLED",
                    role=UserRole.ADMIN,
                )
                session.add(user)
                await session.flush()
                user_id = user.id
                workspace = Workspace(name="Cache race", owner_id=user_id)
                session.add(workspace)
                await session.flush()
                workspace_id = workspace.id
                project = Project(name="Cache race", workspace_id=workspace_id)
                session.add(project)
                await session.flush()
                project_id = project.id
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_task_cache] = lambda: task_page_cache
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app),
                base_url="http://testserver",
                headers={"Authorization": "Bearer " + create_access_token(user_id)},
            ) as client:
                yield client, factory, project_id
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


async def test_concurrent_commits_do_not_lose_cache_version_increments(
    committed_cache_client,
):
    client, factory, project_id = committed_cache_client
    path = project_tasks(project_id)
    assert (await client.get(path)).json()["total"] == 0
    responses = await asyncio.gather(
        *[client.post(path, json={"title": title}) for title in ("First", "Second")]
    )
    assert all(response.status_code == 201 for response in responses)
    assert await version(factory, project_id) == 2
    for _ in range(2):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert {item["title"] for item in response.json()["items"]} == {
            "First",
            "Second",
        }
