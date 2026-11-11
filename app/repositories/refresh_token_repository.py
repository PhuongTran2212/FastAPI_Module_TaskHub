# app/repositories/refresh_token_repository.py
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RefreshToken)

    async def get_by_jti(
        self,
        jti: str,
        *,
        for_update: bool = False,
    ) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)

        if for_update:
            # Khóa dòng: 2 request refresh cùng lúc không thể cùng dùng 1 token
            stmt = stmt.with_for_update()

        return await self.session.scalar(stmt)

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: int) -> None:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
