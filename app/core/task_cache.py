"""Best-effort Redis storage for versioned, authorized task-list reads."""

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import ValidationError
from redis.asyncio import BlockingConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.constants import TASK_CACHE_TTL_SECONDS
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.task import TaskPage

logger = logging.getLogger(__name__)


class TaskPageCache:
    def __init__(
        self,
        client: Redis | None,
        *,
        namespace: str,
        ttl_seconds: int = TASK_CACHE_TTL_SECONDS,
    ) -> None:
        self.client = client
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds

    def key(
        self,
        project_id: int,
        version: int,
        *,
        page: int,
        limit: int,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> str:
        query = json.dumps(
            [page, limit, status, priority, assignee_id], separators=(",", ":")
        )
        digest = hashlib.sha256(query.encode()).hexdigest()
        return f"{self.namespace}:project:{project_id}:v:{version}:{digest}"

    async def get(self, key: str) -> TaskPage | None:
        if self.client is None:
            return None
        try:
            value = await self.client.get(key)
            return TaskPage.model_validate_json(value) if value is not None else None
        except (RedisError, OSError):
            # Never log a connection URL, credential, or cached task content.
            logger.warning("Task cache read unavailable; using PostgreSQL")
        except ValidationError:
            logger.warning("Invalid task cache payload; using PostgreSQL")
        return None

    async def put(self, key: str, page: TaskPage) -> None:
        if self.client is None:
            return
        try:
            await self.client.set(key, page.model_dump_json(), ex=self.ttl_seconds)
        except (RedisError, OSError):
            logger.warning("Task cache write unavailable; response uses PostgreSQL")


def database_cache_namespace(database_url: str) -> str:
    # Isolate databases without embedding usernames/passwords in Redis keys.
    url = make_url(database_url)
    location = json.dumps([url.host, url.port or 5432, url.database])
    digest = hashlib.sha256(location.encode()).hexdigest()[:16]
    return f"taskhub:task-page:v1:{digest}"


@asynccontextmanager
async def task_cache_lifespan(settings: Settings) -> AsyncIterator[TaskPageCache]:
    client = None
    if settings.task_cache_enabled:
        pool = BlockingConnectionPool.from_url(
            str(settings.redis_url),
            socket_connect_timeout=settings.redis_timeout_seconds,
            socket_timeout=settings.redis_timeout_seconds,
            max_connections=settings.redis_max_connections,
            timeout=settings.redis_pool_wait_seconds,
            retry=Retry(NoBackoff(), 0),
            protocol=2,
        )
        client = Redis.from_pool(pool)
    cache = TaskPageCache(
        client,
        namespace=database_cache_namespace(settings.database_url),
        ttl_seconds=settings.task_cache_ttl_seconds,
    )
    try:
        if client is not None:
            try:
                await client.ping()
                logger.info("Task cache Redis connection ready")
            except (RedisError, OSError):
                # Keep the client: later requests can reconnect after Redis recovers.
                logger.warning("Redis unavailable at startup; using PostgreSQL")
        yield cache
    finally:
        if client is not None:
            try:
                await client.aclose()
            except (RedisError, OSError):
                logger.warning("Redis connection cleanup failed")
