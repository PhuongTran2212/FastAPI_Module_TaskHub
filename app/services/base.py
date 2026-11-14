from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import messages
from app.core.exceptions import ConflictException


class TransactionalService:
    """Mỗi phương thức service chạy trong một transaction.

    Lỗi ràng buộc DB (IntegrityError) được chuyển thành 409.
    """

    conflict_message = messages.DATA_CONFLICT

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        try:
            async with self.session.begin():
                yield
        except IntegrityError as exc:
            raise ConflictException(self.conflict_message) from exc
