import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.core import messages
from app.core.constants import BCRYPT_MAX_BYTES
from app.main import app
from app.models import RefreshToken, User
from tests.auth_helpers import EMAIL, PASSWORD, bearer, login, register
from tests.conftest import TEST_DATABASE_URL


async def test_register_and_duplicate_email(client):
    user = await register(
        client, email="  PERSON@Example.com  ", full_name="  Person  "
    )
    assert user["email"] == "person@example.com"
    assert user["full_name"] == "Person"
    assert user["role"] == "MEMBER"
    assert "hashed_password" not in user
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "PERSON@example.com",
            "password": PASSWORD,
            "full_name": "Duplicate",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": messages.EMAIL_ALREADY_REGISTERED}


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_name", "   "),
        ("password", "short"),
        ("password", "a" * (BCRYPT_MAX_BYTES + 1)),
        ("password", "\U0001f600" * 20),
        ("role", "ADMIN"),
    ],
)
async def test_register_validation(client, field, value):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "full_name": "User",
            field: value,
        },
    )
    assert response.status_code == 422


async def test_password_whitespace_is_preserved(client):
    password = "  leading and trailing  "
    await register(client, password=password)
    await login(client, password=password)
    response = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": password.strip()}
    )
    assert response.status_code == 401


async def test_wrong_email_and_password_have_identical_response(client):
    await register(client)
    wrong_email = await client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": PASSWORD},
    )
    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "Wrong-password123!"}
    )
    assert wrong_email.status_code == wrong_password.status_code == 401
    assert (
        wrong_email.json()
        == wrong_password.json()
        == {"detail": messages.INVALID_CREDENTIALS}
    )
    assert (
        wrong_email.headers["www-authenticate"]
        == wrong_password.headers["www-authenticate"]
        == "Bearer"
    )


async def test_login_password_length_is_capped(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "a" * (BCRYPT_MAX_BYTES + 1)},
    )
    assert response.status_code == 422


async def test_refresh_rotation_and_reuse_revokes_all_sessions(client, session_factory):
    user = await register(client)
    original = await login(client)
    other_device = await login(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != original["refresh_token"]
    reused = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert reused.status_code == 401
    assert reused.headers["www-authenticate"] == "Bearer"
    for token in (rotated["refresh_token"], other_device["refresh_token"]):
        assert (
            await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        ).status_code == 401
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(RefreshToken).where(RefreshToken.user_id == user["id"])
            )
        ).all()
        assert rows and all(row.revoked_at is not None for row in rows)


async def test_refresh_token_cannot_be_used_as_access(client):
    await register(client)
    tokens = await login(client)
    response = await client.get(
        "/__test__/protected", headers=bearer(tokens["refresh_token"])
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    response = await client.get(
        "/__test__/protected", headers=bearer(tokens["access_token"])
    )
    assert response.status_code == 200


async def test_access_token_cannot_be_used_as_refresh(client):
    await register(client)
    tokens = await login(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401


async def test_logout_revokes_refresh_and_is_idempotent(client):
    await register(client)
    tokens = await login(client)
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 204 and response.content == b""
    assert (
        await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
    ).status_code == 401


async def test_disabled_user_is_forbidden(client, session_factory):
    user = await register(client)
    tokens = await login(client)
    async with session_factory() as session:
        async with session.begin():
            stored = await session.get(User, user["id"])
            stored.is_active = False
    response = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": messages.ACCOUNT_DISABLED}
    response = await client.get(
        "/__test__/protected", headers=bearer(tokens["access_token"])
    )
    assert response.status_code == 403


@pytest_asyncio.fixture
async def concurrent_client(migrated_database):
    # Separate connections and real commits are required to exercise FOR UPDATE.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    email = "parallel-" + uuid.uuid4().hex + "@example.com"

    async def override():
        async with factory() as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app), base_url="http://testserver"
            ) as client:
                yield client, email, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        async with factory() as session:
            async with session.begin():
                await session.execute(delete(User).where(User.email == email))
        await engine.dispose()


async def test_concurrent_refresh_one_rotates_one_revokes_every_session(
    concurrent_client,
):
    client, email, factory = concurrent_client
    user = await register(client, email=email)
    tokens = await login(client, email=email)
    other = await login(client, email=email)
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    async with factory() as session:
        rows = (
            await session.scalars(
                select(RefreshToken).where(RefreshToken.user_id == user["id"])
            )
        ).all()
        assert len(rows) == 3 and all(row.revoked_at is not None for row in rows)
    for token in (winner["refresh_token"], other["refresh_token"]):
        assert (
            await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        ).status_code == 401


async def test_concurrent_registration_returns_201_and_409(concurrent_client):
    client, email, _ = concurrent_client
    payload = {"email": email, "password": PASSWORD, "full_name": "Concurrent"}
    responses = await asyncio.gather(
        *[client.post("/api/v1/auth/register", json=payload) for _ in range(2)]
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
