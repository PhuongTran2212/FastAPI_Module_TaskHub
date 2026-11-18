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

- Every `/tasks` endpoint requires login. Day 3 does not check ownership: any
  logged-in user can update or delete any task. Owner/role checks for
  update/delete are Day 4.

## Follow-ups

- Day 7: the `refresh_tokens` table only grows (rows are revoked, never
  deleted). Add a Celery beat job that deletes rows whose `expires_at` has
  passed. Revoked rows must be kept until they expire, otherwise reuse of a
  stolen token could no longer be detected.

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
