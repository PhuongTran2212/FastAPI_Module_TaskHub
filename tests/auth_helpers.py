from httpx import AsyncClient

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
