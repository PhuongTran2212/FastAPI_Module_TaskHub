# Day 3 authentication behavior

- Refresh rotation is strict and has no grace window. Clients must serialize
  refresh calls (single-flight) across retries or tabs.
- Reusing a revoked refresh token revokes every refresh token for that user.
  With two simultaneous requests for the same token, one rotation succeeds,
  the other returns 401 and revokes even the new refresh token from the winner.
- Access tokens are stateless JWTs. Logout, refresh reuse, and password changes
  revoke refresh sessions; previously issued access tokens remain valid until
  their expiry (15 minutes by default). Immediate access invalidation is outside
  this Day 3 change.
- Every task endpoint requires login in the task-auth PR. Owner/role checks for
  updating or deleting tasks belong to Day 4.
- Day 7 follow-up: schedule expired-refresh-token cleanup with Celery beat.
  Keep revoked entries until expiry so reuse detection can still identify them.

## Private configuration

Copy .env.example to .env and generate a new private secret:

    openssl rand -hex 32

Python alternative:

    python -c "import secrets; print(secrets.token_hex(32))"

The sample CHANGE_ME cannot satisfy the configured minimum key length.
Changing the signing key invalidates tokens signed with the old key.

## Tests and formatting

Use the dedicated PostgreSQL test database in .env.test, then run:

    python -m pytest -q
    python -m ruff check app tests scripts
    python -m ruff format --check app tests scripts

The concurrency tests use independent database connections and real commits,
so PostgreSQL row locking and the committed reuse revocation are exercised.
