"""Exercise the Compose API -> Redis -> Celery -> Mailpit flow, plus beat cleanup.

Run against a local, disposable Compose stack; no external SMTP is used.
"""

import json
import secrets
import subprocess
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8000/api/v1"
MAILPIT = "http://127.0.0.1:8025/api/v1/messages"
ResultT = TypeVar("ResultT")


def request(
    method: str,
    url: str,
    data: dict[str, object] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    payload = None if data is None else json.dumps(data).encode()
    with urlopen(
        Request(url, data=payload, headers=headers, method=method), timeout=10
    ) as response:
        content = response.read()
        body = json.loads(content) if content else {}
        if not isinstance(body, dict):
            raise AssertionError("Expected an object in the API response")
        return body


def wait_for(check: Callable[[], ResultT], *, timeout: float = 60) -> ResultT:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(1)
    raise AssertionError("Background work did not finish before the timeout")


def compose_python(source: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-c", source],
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def main() -> None:
    suffix = uuid.uuid4().hex
    email = f"smoke-{suffix}@example.com"
    password = secrets.token_hex(24)
    user = request(
        "POST",
        f"{API}/auth/register",
        {
            "email": email,
            "password": password,
            "full_name": "Compose smoke",
        },
    )
    workspace: dict[str, Any] | None = None
    try:
        auth = request(
            "POST", f"{API}/auth/login", {"email": email, "password": password}
        )
        access = auth["access_token"]
        workspace = request(
            "POST", f"{API}/workspaces", {"name": f"Smoke {suffix}"}, access
        )
        project = request(
            "POST",
            f"{API}/workspaces/{workspace['id']}/projects",
            {"name": "Background jobs"},
            access,
        )
        task = request(
            "POST",
            f"{API}/projects/{project['id']}/tasks",
            {
                "title": f"Smoke assignment {suffix}",
                "assignee_id": user["id"],
            },
            access,
        )
        subject = f"TaskHub assignment #{task['id']}"

        def matching_messages() -> list[dict[str, Any]]:
            return [
                message
                for message in request("GET", MAILPIT)["messages"]
                if message["Subject"] == subject
                and any(recipient["Address"] == email for recipient in message["To"])
            ]

        assert len(wait_for(matching_messages)) == 1
        request(
            "PATCH", f"{API}/tasks/{task['id']}", {"assignee_id": user["id"]}, access
        )
        time.sleep(3)
        assert len(matching_messages()) == 1, "Unchanged assignment sent a duplicate"

        # Beat removes only the expired token; keep a revoked future token so
        # reuse detection is still possible. Test rows belong to this new user.
        marker = f"smoke-{suffix}"
        compose_python(f"""
import asyncio
from datetime import UTC, datetime, timedelta
from app.jobs import job_session
from app.models import RefreshToken
async def seed():
    async with job_session() as session, session.begin():
        now = datetime.now(UTC)
        session.add_all([
            RefreshToken(user_id={user["id"]}, jti='{marker}-expired', expires_at=now-timedelta(days=1)),
            RefreshToken(user_id={user["id"]}, jti='{marker}-revoked', expires_at=now+timedelta(days=1), revoked_at=now),
        ])
asyncio.run(seed())
""")

        def expired_removed() -> bool:
            return (
                compose_python(f"""
import asyncio
from sqlalchemy import select
from app.jobs import job_session
from app.models import RefreshToken
async def check():
    async with job_session() as session:
        rows = (await session.scalars(select(RefreshToken.jti).where(RefreshToken.jti.in_(['{marker}-expired', '{marker}-revoked'])))).all()
        print('OK' if rows == ['{marker}-revoked'] else 'WAIT')
asyncio.run(check())
""")
                == "OK"
            )

        wait_for(expired_removed)
        print("Compose smoke passed: assignment email, no-op update, beat cleanup.")
    finally:
        if workspace is not None:
            request(
                "DELETE", f"{API}/workspaces/{workspace['id']}", access_token=access
            )
        compose_python(f"""
import asyncio
from sqlalchemy import delete
from app.jobs import job_session
from app.models import User
async def cleanup():
    async with job_session() as session, session.begin():
        await session.execute(delete(User).where(User.id == {user["id"]}))
asyncio.run(cleanup())
""")


if __name__ == "__main__":
    main()
