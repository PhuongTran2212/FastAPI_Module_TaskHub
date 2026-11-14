from datetime import UTC, datetime, timedelta

import pytest

from app.core import messages
from app.core.constants import BCRYPT_MAX_BYTES
from app.core.enums import UserRole
from app.models import User
from tests.auth_helpers import (
    EMAIL,
    PASSWORD,
    access_token_issued_at,
    bearer,
    login,
    register,
)


async def test_read_and_update_my_profile(client):
    user = await register(client)
    tokens = await login(client)
    headers = bearer(tokens["access_token"])
    assert (await client.get("/api/v1/users/me", headers=headers)).json()["id"] == user[
        "id"
    ]
    response = await client.patch(
        "/api/v1/users/me", headers=headers, json={"full_name": "  Updated  "}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated"


@pytest.mark.parametrize("value", ["   ", None])
async def test_profile_rejects_blank_and_null(client, value):
    response = await client.patch("/api/v1/users/me", json={"full_name": value})
    assert response.status_code == 422


async def test_users_list_requires_admin_and_returns_total(
    client, session_factory, seed_data
):
    assert (await client.get("/api/v1/users")).status_code == 403
    async with session_factory() as session:
        async with session.begin():
            user = await session.get(User, seed_data["creator_id"])
            user.role = UserRole.ADMIN
    response = await client.get("/api/v1/users", params={"page": 2, "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2 and body["page"] == 2 and body["limit"] == 1
    assert len(body["items"]) == 1
    assert (await client.get("/api/v1/users", params={"page": 0})).status_code == 422
    assert (await client.get("/api/v1/users", params={"limit": 101})).status_code == 422


async def test_change_password_revokes_refresh_and_older_access_tokens(client):
    user = await register(client)
    first = await login(client)
    second = await login(client)
    headers = bearer(first["access_token"])
    response = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "New-password123!"},
    )
    assert response.status_code == 204 and response.content == b""
    # An access token issued before the change is rejected right away.
    issued_before = datetime.now(UTC) - timedelta(minutes=1)
    old_access = access_token_issued_at(user["id"], issued_before)
    response = await client.get("/api/v1/users/me", headers=bearer(old_access))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    for token in (first["refresh_token"], second["refresh_token"]):
        assert (
            await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
    ).status_code == 401
    fresh = await login(client, password="New-password123!")
    response = await client.get(
        "/api/v1/users/me", headers=bearer(fresh["access_token"])
    )
    assert response.status_code == 200


async def test_incorrect_current_password(client):
    await register(client)
    tokens = await login(client)
    response = await client.post(
        "/api/v1/users/me/password",
        headers=bearer(tokens["access_token"]),
        json={
            "current_password": "Incorrect-password",
            "new_password": "New-password123!",
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": messages.INCORRECT_CURRENT_PASSWORD}


@pytest.mark.parametrize("field", ["current_password", "new_password"])
async def test_change_password_limits_input(client, field):
    payload = {
        "current_password": PASSWORD,
        "new_password": "New-password123!",
        field: "x" * (BCRYPT_MAX_BYTES + 1),
    }
    assert (
        await client.post("/api/v1/users/me/password", json=payload)
    ).status_code == 422
