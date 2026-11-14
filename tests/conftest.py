import itertools
import os
import secrets
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]


def load_test_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL") or dotenv_values(
        ROOT / ".env.test"
    ).get("TEST_DATABASE_URL")
    if not value:
        raise pytest.UsageError(
            "Set TEST_DATABASE_URL or create .env.test using .env.test.example."
        )
    try:
        test_url = make_url(value)
    except Exception:
        raise pytest.UsageError("TEST_DATABASE_URL is not a valid URL.") from None
    if test_url.drivername != "postgresql+asyncpg" or not (
        test_url.database and test_url.database.endswith("_test")
    ):
        raise pytest.UsageError(
            "Tests require postgresql+asyncpg and a database name ending in _test."
        )

    application_value = os.environ.get("DATABASE_URL") or dotenv_values(
        ROOT / ".env"
    ).get("DATABASE_URL")
    if application_value:
        application_url = make_url(application_value)
        if (test_url.host, test_url.port or 5432, test_url.database) == (
            application_url.host,
            application_url.port or 5432,
            application_url.database,
        ):
            raise pytest.UsageError("The test and application databases must differ.")
    return value


TEST_DATABASE_URL = load_test_database_url()
# Configure before importing the app so its lifespan uses the test DB too.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)

from app.api.deps import CurrentUser  # noqa: E402
from app.core.enums import UserRole, WorkspaceRole  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Project, User, Workspace, WorkspaceMember  # noqa: E402


def run_alembic(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


@pytest.fixture(scope="session")
def migrated_database() -> None:
    # Run the actual migrations instead of creating tables from model metadata.
    run_alembic("upgrade", "head")


@pytest.fixture
def alembic_runner(migrated_database) -> Callable[..., str]:
    return run_alembic


@pytest_asyncio.fixture
async def db_connection(migrated_database) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                yield connection
            finally:
                if transaction.is_active:
                    await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(db_connection) -> async_sessionmaker[AsyncSession]:
    # Request commits release savepoints. The test's outer transaction rolls back
    # all changes, including seed data, after each test.
    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def seed_data(session_factory) -> dict[str, int]:
    async with session_factory() as session:
        async with session.begin():
            creator = User(
                email="creator@example.test",
                full_name="Creator",
                hashed_password="TEST_LOGIN_DISABLED",
            )
            assignee = User(
                email="assignee@example.test",
                full_name="Assignee",
                hashed_password="TEST_LOGIN_DISABLED",
            )
            session.add_all([creator, assignee])
            await session.flush()
            workspace = Workspace(name="Test workspace", owner_id=creator.id)
            session.add(workspace)
            await session.flush()
            # creator (người gọi API mặc định) là OWNER, assignee là EDITOR
            session.add_all(
                [
                    WorkspaceMember(
                        workspace_id=workspace.id,
                        user_id=creator.id,
                        role=WorkspaceRole.OWNER,
                    ),
                    WorkspaceMember(
                        workspace_id=workspace.id,
                        user_id=assignee.id,
                        role=WorkspaceRole.EDITOR,
                    ),
                ]
            )
            await session.flush()
            project = Project(name="Project A", workspace_id=workspace.id)
            other_project = Project(name="Project B", workspace_id=workspace.id)
            session.add_all([project, other_project])
            await session.flush()
            return {
                "creator_id": creator.id,
                "assignee_id": assignee.id,
                "workspace_id": workspace.id,
                "project_id": project.id,
                "other_project_id": other_project.id,
            }


@pytest_asyncio.fixture
async def client(session_factory, seed_data) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app),
                base_url="http://testserver",
                headers={
                    "Authorization": "Bearer "
                    + create_access_token(seed_data["creator_id"])
                },
            ) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


MakeUser = Callable[..., Awaitable[dict]]


@pytest.fixture
def make_user(session_factory) -> MakeUser:
    """Tạo user trực tiếp trong DB, trả về id, email và header Bearer."""
    counter = itertools.count(1)

    async def factory(role: UserRole = UserRole.MEMBER) -> dict:
        number = next(counter)
        async with session_factory() as session:
            async with session.begin():
                user = User(
                    email=f"user{number}@example.com",
                    full_name=f"User {number}",
                    hashed_password="TEST_LOGIN_DISABLED",
                    role=role,
                )
                session.add(user)
                await session.flush()
                return {
                    "id": user.id,
                    "email": user.email,
                    "headers": {
                        "Authorization": "Bearer " + create_access_token(user.id)
                    },
                }

    return factory


@app.get("/__test__/protected", include_in_schema=False)
async def protected_test_route(current_user: CurrentUser) -> dict[str, int]:
    return {"id": current_user.id}
