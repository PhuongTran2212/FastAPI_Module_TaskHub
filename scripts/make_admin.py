# scripts/make_admin.py
import asyncio
import sys

from app.core.enums import UserRole
from app.db.session import SessionFactory, engine
from app.repositories.user_repository import UserRepository


async def main(email: str) -> None:
    try:
        async with SessionFactory() as session:
            async with session.begin():
                users = UserRepository(session)
                user = await users.get_by_email(email.strip().lower())

                if user is None:
                    print(f"User {email} not found")
                    return

                await users.update(user, {"role": UserRole.ADMIN})
                print(f"{user.email} is now ADMIN")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.make_admin <email>")
        raise SystemExit(1)

    asyncio.run(main(sys.argv[1]))
