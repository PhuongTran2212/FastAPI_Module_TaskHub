import asyncio

from sqlalchemy.exc import IntegrityError

from app.core import messages
from app.core.config import get_settings
from app.core.constants import SECONDS_PER_MINUTE
from app.core.enums import TokenType
from app.core.exceptions import (
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    InvalidRefreshToken,
    TokenError,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead


class AuthService:
    def __init__(
        self, users: UserRepository, refresh_tokens: RefreshTokenRepository
    ) -> None:
        self.users = users
        self.refresh_tokens = refresh_tokens
        self.session = users.session

    async def register(self, data: RegisterRequest) -> UserRead:
        hashed_password = await asyncio.to_thread(hash_password, data.password)
        try:
            async with self.session.begin():
                if await self.users.get_by_email(data.email) is not None:
                    raise EmailAlreadyRegistered()
                user = await self.users.create(
                    {
                        "email": data.email,
                        "full_name": data.full_name,
                        "hashed_password": hashed_password,
                    }
                )
                return UserRead.model_validate(user)
        except IntegrityError as exc:
            # Translate the email unique violation, not unrelated DB failures.
            if (
                getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
                == "uq_users_email"
            ):
                raise EmailAlreadyRegistered() from exc
            raise

    async def login(self, data: LoginRequest) -> TokenResponse:
        async with self.session.begin():
            user = await self.users.get_by_email(data.email)
        hashed_password = (
            user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
        )
        password_ok = await asyncio.to_thread(
            verify_password, data.password, hashed_password
        )
        if user is None or not password_ok:
            raise InvalidCredentials()
        if not user.is_active:
            raise InactiveUser()
        async with self.session.begin():
            return await self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        payload = self._decode_refresh_token(refresh_token)
        async with self.session.begin():
            stored = await self.refresh_tokens.get_by_jti(payload.jti, for_update=True)
            if stored is None or stored.user_id != payload.user_id:
                raise InvalidRefreshToken()
            if stored.revoked_at is None:
                user = await self.users.get(stored.user_id)
                if user is None or not user.is_active:
                    raise InvalidRefreshToken()
                await self.refresh_tokens.revoke(stored)
                return await self._issue_tokens(user.id)
            # Commit reuse revocation before returning 401; raising inside the
            # transaction would roll back the revocation.
            await self.refresh_tokens.revoke_all_for_user(stored.user_id)
        raise InvalidRefreshToken(messages.REFRESH_TOKEN_REVOKED)

    async def logout(self, refresh_token: str) -> None:
        payload = self._decode_refresh_token(refresh_token)
        async with self.session.begin():
            stored = await self.refresh_tokens.get_by_jti(payload.jti, for_update=True)
            if (
                stored is not None
                and stored.user_id == payload.user_id
                and stored.revoked_at is None
            ):
                await self.refresh_tokens.revoke(stored)

    async def _issue_tokens(self, user_id: int) -> TokenResponse:
        refresh_token, jti, expires_at = create_refresh_token(user_id)
        await self.refresh_tokens.create(
            {"user_id": user_id, "jti": jti, "expires_at": expires_at}
        )
        return TokenResponse(
            access_token=create_access_token(user_id),
            refresh_token=refresh_token,
            expires_in=get_settings().access_token_expire_minutes * SECONDS_PER_MINUTE,
        )

    @staticmethod
    def _decode_refresh_token(token: str) -> TokenPayload:
        try:
            return decode_token(token, TokenType.REFRESH)
        except TokenError as exc:
            raise InvalidRefreshToken() from exc
