import uuid
from datetime import datetime, timedelta

import jwt
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.enums import TokenType

PASSWORD = "Correct-password123!"
EMAIL = "auth-user@example.com"


async def register(
    client: AsyncClient, email: str = EMAIL, password: str = PASSWORD, **fields
) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Auth User",
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(
    client: AsyncClient, email: str = EMAIL, password: str = PASSWORD
) -> dict:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def access_token_issued_at(user_id: int, issued_at: datetime) -> str:
    """Signed access token with a chosen iat (JWT iat has 1-second precision)."""
    settings = get_settings()
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": TokenType.ACCESS.value,
            "jti": uuid.uuid4().hex,
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
