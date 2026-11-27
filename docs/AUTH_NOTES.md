# Day 3 authentication behavior

## Refresh token rotation

- Rotation is strict and has **no grace window**. Each refresh token can be
  used once; using it revokes it and returns a new access/refresh pair.
- Reusing a revoked refresh token is treated as theft: every refresh token of
  that user is revoked and the request gets 401.
- Two tabs (or a client retry) refreshing with the same token at the same time:
  the row lock (`SELECT ... FOR UPDATE`) lets one request rotate and return 200;
  the other sees a revoked token, returns 401 and revokes every session,
  including the new token the first request just issued. The user has to log in
  again.
- This is accepted on purpose: a grace window would let a stolen token be
  replayed within that window. Clients must refresh single-flight (one shared
  in-flight refresh per browser/app, other callers wait for its result) and
  must not blindly retry a refresh that may have reached the server.

## Access tokens

- Access tokens are stateless JWTs (15 minutes by default).
- Logout revokes only the given refresh token; an access token already issued
  stays valid until it expires.
- Changing the password stores `users.password_changed_at` and revokes every
  refresh token. `get_current_user` rejects any access token whose `iat` is
  earlier than `password_changed_at`, so old access tokens stop working
  immediately. JWT `iat` has 1-second precision: a token issued within the same
  second as the change is still accepted.

## Tasks

- Every task endpoint requires login. Since Day 4, workspace roles and task
  ownership decide who can read, update and delete; see docs/RBAC.md.

## Day 7: background jobs

Celery workers send assignment emails; one Celery beat process schedules
refresh-token cleanup. Redis DB 1 is the broker, separate from the Day 6 cache
in DB 0. Jobs accept JSON IDs only and do not store results.

### Assignment emails

- Creating an assigned task or changing its assignee to another user queues
  one notification after the database transaction commits. FastAPI
  `BackgroundTasks` publishes to Celery in a thread after the response.
- Unassigned tasks, unchanged assignees, clearing the assignee, unrelated
  updates, rejected requests and rolled-back transactions do not enqueue email.
- The worker reads the current task/user/membership. Deleted or reassigned tasks,
  inactive users and users who are no longer OWNER/EDITOR are skipped. The
  recipient is read from the database, never supplied in the queue message.
- Transient SMTP/connectivity failures retry up to `JOB_MAX_RETRIES` (3 by default) with exponential
  backoff and jitter. SMTP reply codes 4xx (including recipient greylisting) retry;
  5xx and TLS certificate verification errors do not. Notification messages expire
  after 1 hour by default.
  SMTP authentication requires TLS (`starttls` or `ssl`), with certificate
  verification. Logs omit email addresses, task titles and SMTP credentials.
- This is best-effort delivery: a broker outage is logged and leaves the task
  saved; an API process crash between commit and publication can lose an email.
  There is no transactional outbox or exactly-once delivery. Failures after SMTP acceptance during QUIT do not retry and log at INFO,
  separately from delivery failures. Ambiguous failures during DATA can
  still duplicate an email; the job keeps the same Message-ID across its retries.
  Membership/task changes after the worker's read can race with SMTP delivery.

### Expired refresh tokens

- Every 300 seconds, beat schedules a cleanup of batches of 500 expired rows,
  ordered by expiry and ID, until the backlog is drained or the 30-second budget expires.
  Each batch commits independently. `expires_at` has an index (migration `7b019dca0001`).
- `FOR UPDATE SKIP LOCKED` makes overlapping cleanup workers select disjoint
  batches; deletion commits atomically. Re-running a batch is safe.
- Both active and revoked **expired** rows are deleted. Revoked but unexpired
  tokens remain available for reuse detection. Access-token behavior is unchanged.
- Configure `REFRESH_CLEANUP_INTERVAL_SECONDS` and
  `REFRESH_CLEANUP_BATCH_SIZE` and `REFRESH_CLEANUP_BUDGET_SECONDS` for the expected volume. Run only one beat process;
  old queued cleanup jobs expire after one interval.

### Run the full stack (recommended on Windows)

Install Docker Desktop with Linux containers. From the repository root, copy
`.env.example` to `.env` only if you do not already have one, then generate a
private `JWT_SECRET_KEY` as described below. Keep `.env` out of Git.

```powershell
docker compose up --build --wait
docker compose ps
```

Compose starts PostgreSQL 16, Redis 7, Mailpit, the API, a Celery worker and one
beat process. A one-off migration must succeed before API/worker/beat start.
The image uses a multi-stage build and runs as a non-root user; `.env`, tests,
Git data and the local venv are excluded from its build context.

- Swagger: http://127.0.0.1:8000/docs
- Mailpit inbox: http://127.0.0.1:8025 (captures email locally; no external delivery)
- Stop a locally running Uvicorn first if port 8000 is already in use.
- Compose uses its own PostgreSQL volume. Your host `taskhub_day2`/`taskhub`
  database is not used. Container hostnames override `.env` connection URLs.
- The sample `POSTGRES_PASSWORD=taskhub_dev` is for this local stack. Changing
  it later does not change a password stored in an existing volume.

In Swagger: register/login, authorize, create a workspace and project, then
create a task with your user ID as `assignee_id`. Confirm one email in Mailpit.
PATCH the same assignee: no extra email. PATCH another eligible member: that
member receives an email. Clearing the assignee sends nothing.

```powershell
docker compose logs --tail 100 worker beat
docker compose stop
# Restart and preserve database/Redis volumes:
docker compose up --wait
```

For local processes without Docker: install `requirements-dev.txt`, apply
migrations, start PostgreSQL/Redis/a local SMTP catcher, and set
`ASSIGNMENT_EMAIL_ENABLED=true` with the corresponding SMTP settings. Start the
API and each command below in separate terminals with the same `.env`:

```text
python -m celery -A app.core.celery_app:celery_app worker --loglevel=INFO
python -m celery -A app.core.celery_app:celery_app beat --loglevel=INFO
```

Use Linux/WSL/Docker for Celery workers; native Windows is not supported by
Celery. Keep one beat process. Email is disabled by default outside Compose.

### Verification

`tests/test_background.py` exercises notification triggers, rollback, RBAC,
broker failure, stale assignments, SMTP delivery/retry through loopback SMTP,
configuration, cleanup boundaries/batches and concurrent PostgreSQL row locks.
The existing migration test downgrades/upgrades and checks metadata parity.
Unit/API tests disable external email regardless of the developer's `.env`.

CI also builds the actual image and runs `scripts/smoke_background.py` against
the Compose stack: API -> Redis -> Celery -> Mailpit, unchanged assignment, and
beat-driven cleanup that retains an unexpired revoked token. The script is for
a local test stack only; it creates temporary accounts/workspaces and removes
them afterwards. To run it manually, start a separate disposable Compose
project with `REFRESH_CLEANUP_INTERVAL_SECONDS=5`; the smoke timeout is 60 seconds.

## Private configuration

Copy .env.example to .env and generate a new private secret:

    openssl rand -hex 32

Python alternative:

    python -c "import secrets; print(secrets.token_hex(32))"

The sample CHANGE_ME cannot satisfy the configured minimum key length.
Changing the signing key invalidates tokens signed with the old key.

## Migrations, tests and formatting

Apply the migrations (adds `refresh_tokens` and `users.password_changed_at`):

    python -m alembic upgrade head

Use the dedicated PostgreSQL test database in .env.test, then run:

    python -m pytest -q
    python -m ruff check app tests scripts
    python -m ruff format --check app tests scripts

The concurrency tests use independent database connections and real commits,
so PostgreSQL row locking and the committed reuse revocation are exercised.
