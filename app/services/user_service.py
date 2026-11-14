# app/services/user_service.py
import asyncio

from app.core.exceptions import IncorrectPassword
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import ChangePasswordRequest, UserRead, UserUpdate


class UserService:
    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
    ) -> None:
        self.users = users
        self.refresh_tokens = refresh_tokens
        self.session = users.session

    async def list_users(self, page: int, limit: int) -> list[UserRead]:
        users = await self.users.list(offset=(page - 1) * limit, limit=limit)
        return [UserRead.model_validate(user) for user in users]

    async def update_profile(self, user: User, data: UserUpdate) -> UserRead:
        async with self.session.begin():
            updated = await self.users.update(
                user,
                data.model_dump(exclude_unset=True),
            )
            return UserRead.model_validate(updated)

    async def change_password(
        self,
        user: User,
        data: ChangePasswordRequest,
    ) -> None:
        password_ok = await asyncio.to_thread(
            verify_password,
            data.current_password,
            user.hashed_password,
        )
        if not password_ok:
            raise IncorrectPassword()

        new_hash = await asyncio.to_thread(hash_password, data.new_password)

        async with self.session.begin():
            await self.users.update(user, {"hashed_password": new_hash})
            # Đổi mật khẩu → đăng xuất mọi thiết bị
            await self.refresh_tokens.revoke_all_for_user(user.id)
