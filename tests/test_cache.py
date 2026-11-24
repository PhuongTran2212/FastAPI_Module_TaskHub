import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis import FakeAsyncRedis
from pydantic import ValidationError
from redis.asyncio import BlockingConnectionPool
from redis.asyncio.connection import Connection
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.enums import TaskPriority, TaskStatus
from app.core.task_cache import (
    TaskPageCache,
    database_cache_namespace,
    task_cache_lifespan,
)
from app.schemas.task import TaskPage


def sample_page():
    return TaskPage(items=[], total=0, page=1, limit=20)


async def test_cache_serialization_and_expiry(task_page_cache):
    cache = task_page_cache
    cache.ttl_seconds = 1
    key = cache.key(1, 0, page=1, limit=20)
    assert await cache.get(key) is None
    await cache.put(key, sample_page())
    assert await cache.get(key) == sample_page()
    assert 0 < await cache.client.ttl(key) <= 1
    await asyncio.sleep(1.1)
    assert await cache.get(key) is None


def test_key_covers_every_filter_project_and_generation():
    cache = TaskPageCache(None, namespace="test")
    defaults = {"project_id": 1, "version": 0, "page": 1, "limit": 20}
    variants = [
        {"project_id": 2},
        {"version": 1},
        {"page": 2},
        {"limit": 10},
        {"status": TaskStatus.DONE},
        {"priority": TaskPriority.HIGH},
        {"assignee_id": 7},
    ]
    keys = [cache.key(**defaults)] + [
        cache.key(**{**defaults, **query}) for query in variants
    ]
    assert len(set(keys)) == len(keys)
    assert cache.key(**defaults) == cache.key(
        **defaults, status=None, priority=None, assignee_id=None
    )


def test_database_namespaces_isolate_environments_and_hide_credentials():
    first = database_cache_namespace(
        "postgresql+asyncpg://alice:private@localhost:5432/app"
    )
    assert first == database_cache_namespace(
        "postgresql+asyncpg://bob:secret@localhost:5432/app"
    )
    assert first == database_cache_namespace(
        "postgresql+asyncpg://alice:private@localhost/app"
    )
    assert first != database_cache_namespace(
        "postgresql+asyncpg://alice:private@localhost:5432/app_test"
    )
    assert "alice" not in first and "private" not in first


@pytest.mark.parametrize("payload", [b"not JSON", b"{}", b'{"items": "invalid"}'])
async def test_corrupt_payload_is_treated_as_a_miss(task_page_cache, payload):
    cache = task_page_cache
    key = cache.key(1, 0, page=1, limit=20)
    await cache.client.set(key, payload, ex=60)
    assert await cache.get(key) is None
    await cache.put(key, sample_page())
    assert await cache.get(key) == sample_page()


async def test_disabled_cache_does_not_create_redis_connections():
    settings = Settings(_env_file=None, task_cache_enabled=False)
    with patch("app.core.task_cache.Redis.from_pool") as factory:
        async with task_cache_lifespan(settings) as cache:
            assert await cache.get("anything") is None
            await cache.put("anything", sample_page())
        factory.assert_not_called()


async def test_cache_lifespan_closes_pool_even_if_application_fails():
    settings = Settings(_env_file=None, task_cache_enabled=True)
    client = FakeAsyncRedis()
    close = AsyncMock(wraps=client.aclose)
    with patch("app.core.task_cache.Redis.from_pool", return_value=client) as factory:
        with patch.object(client, "aclose", close):
            with pytest.raises(RuntimeError, match="app failure"):
                async with task_cache_lifespan(settings) as cache:
                    assert cache.client is client
                    raise RuntimeError("app failure")
            close.assert_awaited_once()
        assert (
            factory.call_args.args[0].connection_kwargs["socket_timeout"]
            == settings.redis_timeout_seconds
        )
        assert (
            factory.call_args.args[0].connection_kwargs["socket_connect_timeout"]
            == settings.redis_timeout_seconds
        )


async def test_cache_startup_outage_can_recover_without_app_restart():
    settings = Settings(_env_file=None, task_cache_enabled=True)
    client = FakeAsyncRedis()
    with patch("app.core.task_cache.Redis.from_pool", return_value=client):
        with patch.object(
            client, "ping", AsyncMock(side_effect=RedisConnectionError())
        ):
            async with task_cache_lifespan(settings) as cache:
                await cache.put("after-recovery", sample_page())
                assert await cache.get("after-recovery") == sample_page()


@pytest.mark.parametrize(
    "changes",
    [
        {"task_cache_ttl_seconds": 0},
        {"task_cache_ttl_seconds": 3601},
        {"redis_timeout_seconds": 0},
        {"redis_url": "https://example.com"},
    ],
)
def test_settings_reject_invalid_cache_configuration(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


async def test_blocking_pool_waits_for_capacity_and_has_bounded_timeout():
    class LocalConnection(Connection):
        async def connect(self):
            pass

        async def can_read(self):
            return False

    pool = BlockingConnectionPool(
        connection_class=LocalConnection, max_connections=10, timeout=0.1
    )
    held = await asyncio.gather(*[pool.get_connection() for _ in range(10)])
    pending = [asyncio.create_task(pool.get_connection()) for _ in range(5)]
    try:
        await asyncio.sleep(0.01)
        assert all(not task.done() for task in pending)
        await asyncio.gather(*[pool.release(connection) for connection in held])
        acquired = await asyncio.gather(*pending)
        await asyncio.gather(*[pool.release(connection) for connection in acquired])
        held = await asyncio.gather(*[pool.get_connection() for _ in range(10)])
        with pytest.raises(RedisConnectionError, match="No connection available"):
            await pool.get_connection()
    finally:
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.gather(*[pool.release(connection) for connection in held])
        await pool.aclose()


def test_pool_configuration_is_validated():
    for changes in ({"redis_max_connections": 0}, {"redis_pool_wait_seconds": 0}):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **changes)
