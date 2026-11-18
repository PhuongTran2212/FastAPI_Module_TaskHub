# app/services/user_service.py
import asyncio
from datetime import UTC, datetime

from app.core.exceptions import IncorrectPassword
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import ChangePasswordRequest, UserPage, UserRead, UserUpdate


class UserService:
    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
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
        # iat của JWT tính theo giây → làm tròn xuống cùng đơn vị để token
        # đăng nhập lại ngay sau khi đổi mật khẩu vẫn hợp lệ
        changed_at = datetime.now(UTC).replace(microsecond=0)

        async with self.session.begin():
            await self.users.update(
                user,
                {"hashed_password": new_hash, "password_changed_at": changed_at},
            )
            # Đổi mật khẩu → đăng xuất mọi thiết bị: thu hồi refresh token,
            # access token cũ bị chặn nhờ password_changed_at
            await self.refresh_tokens.revoke_all_for_user(user.id)
