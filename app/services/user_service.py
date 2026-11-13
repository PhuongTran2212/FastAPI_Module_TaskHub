import asyncio

from app.core.exceptions import IncorrectPassword
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import ChangePasswordRequest, UserPage, UserRead, UserUpdate


class UserService:
    def __init__(
        self, users: UserRepository, refresh_tokens: RefreshTokenRepository
    ) -> None:
        self.users = users
        self.refresh_tokens = refresh_tokens
        self.session = users.session

    async def list_users(self, page: int, limit: int) -> UserPage:
        users = await self.users.list(offset=(page - 1) * limit, limit=limit)
        return UserPage(
            items=[UserRead.model_validate(user) for user in users],
            total=await self.users.count(),
            page=page,
            limit=limit,
        )

    async def update_profile(self, user: User, data: UserUpdate) -> UserRead:
        async with self.session.begin():
            return UserRead.model_validate(
                await self.users.update(user, data.model_dump(exclude_unset=True))
            )

    async def change_password(self, user: User, data: ChangePasswordRequest) -> None:
        if not await asyncio.to_thread(
            verify_password, data.current_password, user.hashed_password
        ):
            raise IncorrectPassword()
        new_hash = await asyncio.to_thread(hash_password, data.new_password)
        async with self.session.begin():
            await self.users.update(user, {"hashed_password": new_hash})
            await self.refresh_tokens.revoke_all_for_user(user.id)
