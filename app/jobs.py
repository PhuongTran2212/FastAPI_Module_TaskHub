import asyncio
import logging
import smtplib
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.enums import WorkspaceRole
from app.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """A retryable error whose message contains no SMTP credentials or recipient."""


@asynccontextmanager
async def job_session() -> AsyncIterator[AsyncSession]:
    # Celery's sync tasks use asyncio.run per execution; do not reuse an async
    # connection pool across event loops or fork worker processes.
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"timeout": get_settings().job_connection_timeout_seconds},
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


async def assignment_details(task_id: int, assignee_id: int) -> tuple[str, str] | None:
    async with job_session() as session:
        async with session.begin():
            task = await TaskRepository(session).get_with_project(task_id)
            if task is None or task.assignee_id != assignee_id:
                return None
            user = await session.get(User, assignee_id)
            member = await WorkspaceMemberRepository(session).get_member(
                task.project.workspace_id,
                assignee_id,
            )
            if user is None or not user.is_active or member is None:
                return None
            if member.role not in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
                return None
            return user.email, task.title


def deliver_assignment(
    recipient: str, title: str, task_id: int, delivery_id: str
) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = str(settings.smtp_from_email)
    message["To"] = recipient
    message["Subject"] = f"TaskHub assignment #{task_id}"
    message["Message-ID"] = f"<assignment-{delivery_id}@taskhub.local>"
    message.set_content(f"You have been assigned task #{task_id}:\n\n{title}\n")
    smtp_type = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
    tls_options = (
        {"context": ssl.create_default_context()}
        if settings.smtp_security == "ssl"
        else {}
    )
    try:
        with smtp_type(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
            **tls_options,
        ) as connection:
            if settings.smtp_security == "starttls":
                connection.starttls(context=ssl.create_default_context())
            if settings.smtp_username and settings.smtp_password:
                connection.login(
                    settings.smtp_username, settings.smtp_password.get_secret_value()
                )
            connection.send_message(message)
    except (smtplib.SMTPException, OSError):
        raise EmailDeliveryError("SMTP delivery failed") from None


@celery_app.task(
    name="taskhub.send_assignment_email",
    bind=True,
    autoretry_for=(EmailDeliveryError, SQLAlchemyError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=get_settings().job_max_retries,
)
def send_assignment_email(self, task_id: int, assignee_id: int) -> bool:
    if not get_settings().assignment_email_enabled:
        return False
    details = asyncio.run(assignment_details(task_id, assignee_id))
    if details is None:
        return False
    recipient, title = details
    deliver_assignment(recipient, title, task_id, self.request.id or "direct")
    logger.info("Assignment email sent for task_id=%s", task_id)
    return True


async def cleanup_expired_tokens() -> int:
    async with job_session() as session:
        async with session.begin():
            return await RefreshTokenRepository(session).delete_expired_batch(
                datetime.now(UTC),
                limit=get_settings().refresh_cleanup_batch_size,
            )


@celery_app.task(
    name="taskhub.cleanup_expired_refresh_tokens",
    autoretry_for=(SQLAlchemyError, OSError),
    retry_backoff=True,
    max_retries=get_settings().job_max_retries,
)
def cleanup_expired_refresh_tokens() -> int:
    count = asyncio.run(cleanup_expired_tokens())
    logger.info("Expired refresh tokens removed: %s", count)
    return count
