# app/repositories/refresh_token_repository.py
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RefreshToken)

    async def delete_expired_batch(self, cutoff: datetime, *, limit: int) -> int:
        # Keep revoked-but-unexpired tokens for reuse detection. SKIP LOCKED
        # allows overlapping workers without waiting on each other's batch.
        ids = (
            select(RefreshToken.id)
            .where(RefreshToken.expires_at <= cutoff)
            .order_by(RefreshToken.expires_at, RefreshToken.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(
            delete(RefreshToken)
            .where(RefreshToken.id.in_(ids))
            .execution_options(synchronize_session=False)
        )
        return result.rowcount

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
