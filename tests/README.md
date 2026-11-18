# Day 2 PostgreSQL tests

Install the test dependencies from the project root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Create a dedicated database as a PostgreSQL administrator:

```sql
CREATE DATABASE taskhub_day2_test OWNER taskhub;
```

Copy `.env.test.example` to `.env.test` and set the real connection credentials.
Alternatively, set the `TEST_DATABASE_URL` environment variable. The database must
use `postgresql+asyncpg`, have a name ending in `_test`, and differ from the
application database configured in `.env` or `DATABASE_URL`.

Run the suite:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

The suite runs Alembic migrations on the test database, including a downgrade and
upgrade of the review migration. API tests run the real application lifespan and
CRUD through PostgreSQL. Each request has a separate session; savepoints allow
service commits while an outer transaction rolls back each test's data and DDL.

Coverage includes pagination/filter totals, request validation, 404/422/409
responses and rollback recovery, foreign-key deletion behavior, label uniqueness,
and OpenAPI response contracts. Tests exercise PostgreSQL constraints directly.
