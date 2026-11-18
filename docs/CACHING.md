# Day 6: Redis task-list cache

This change caches only `GET /api/v1/projects/{id}/tasks`. The response remains
`items/total/page/limit`. Project existence, the caller's current membership and
role are checked in PostgreSQL before every cache lookup, including cache hits.
All authorized members see the same task list; credentials are never cache keys.

## Setup

Install `requirements.txt`, apply migrations with `python -m alembic upgrade head`,
and configure the new variables from `.env.example`:

```dotenv
REDIS_URL=redis://localhost:6379/0
TASK_CACHE_ENABLED=true
TASK_CACHE_TTL_SECONDS=60
REDIS_TIMEOUT_SECONDS=0.2
```

Use Redis 7. If Docker is installed, start a local development instance with:

```powershell
docker run --name taskhub-redis -p 127.0.0.1:6379:6379 -d redis:7
```

Redis is an optional runtime dependency: a startup or request-time Redis error
logs a warning and falls back to PostgreSQL. Each network operation has a short
timeout and no automatic retries. `TASK_CACHE_ENABLED=false` creates no Redis
client. The app lifespan creates one pool and closes it during shutdown.

## Keys, expiry and invalidation

Keys contain a schema/environment namespace, project ID, the project's committed
`task_cache_version`, and a hash of page, limit, status, priority and assignee ID.
The environment namespace hashes database host/port/name without credentials.
Default TTL is 60 seconds (configurable from 1 to 3600).

The migration adds an internal bigint counter on `projects`. TaskRepository
increments it with an atomic SQL UPDATE in the **same transaction** as each
create/update/delete. Bulk unassignment on member removal increments every
affected project's counter. Failed writes roll back the counter too. The counter
is internal and is not added to API responses.

This is logical invalidation: new reads use a new version, while old Redis keys
expire naturally. No KEYS, global flush, or wildcard deletion is required. A late
cache fill stays under the old version, and a Redis outage cannot lose an
invalidation. Concurrent writes use SQL increments rather than read/modify/write,
so they cannot lose counter increments.

Deleting a project/workspace makes authorization/resource lookup return 404 before
Redis; archive does not change TaskRead data, and existing write restrictions still
apply. Label/comment mutations do not change this task-list response. No response
stores project status, labels, comments or per-user information.

## Consistency and limits

- This remains a PostgreSQL-backed API: cache hits avoid the task/count queries,
  but still execute authentication and authorization/project queries.
- Reads overlapping a committed write may return the previous snapshot. A read
  beginning after a successful write sees its new generation. Late fills cannot
  make that previous generation current again.
- All application task mutations must use TaskRepository. Direct SQL edits outside
  the app must also increment the affected projects' counters. After restoring a
  database backup, clear this app's Redis namespace or wait for its TTL.
- Old versions consume memory until their TTL expires. There is no single-flight
  lock: simultaneous cold reads may perform duplicate PostgreSQL queries.
- Redis is a private cache service; configure network access and credentials for
  the deployment. URL/password/task contents are not written to application logs.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app tests scripts
python -m ruff format --check app tests scripts
```

The existing dedicated PostgreSQL test DB is retained. Cache tests use an isolated
fakeredis Redis-7-compatible store locally. Set `TEST_REDIS_URL` to run the same
tests against a real Redis server, e.g. `redis://localhost:6379/15`. Cleanup deletes
only the test's UUID namespace, never flushes the database. GitHub Actions runs
the suite with PostgreSQL 16 and Redis 7 services.

Coverage includes cache hits, all filters/pages, TTL, corrupt payloads, CRUD and
bulk-unassignment invalidation, membership revocation/cascades, Redis outage and
recovery, rollback after an attempted counter increment, late cache-fill races and
independent concurrent PostgreSQL commits. No email/background task or Day 7
cleanup job is included in this PR.
