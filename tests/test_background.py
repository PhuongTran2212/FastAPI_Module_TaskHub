import asyncio
import smtplib
import socket
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from aiosmtpd.controller import Controller
from fastapi import BackgroundTasks
from kombu.exceptions import OperationalError
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, InterfaceError, ProgrammingError
from sqlalchemy.exc import OperationalError as DBOperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import jobs
from app.api.deps import get_assignment_notifications
from app.core.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.core.enums import WorkspaceRole
from app.main import app
from app.models import RefreshToken, Task, User, WorkspaceMember
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.task_repository import TaskRepository
from app.services import notifications
from app.services.notifications import AssignmentNotifications
from tests.conftest import TEST_DATABASE_URL

REAL_PUBLISHER = notifications.publish_assignment_email


@pytest.fixture
def queued(client, monkeypatch):
    publisher = Mock()
    monkeypatch.setattr(notifications, "publish_assignment_email", publisher)

    def enabled(background: BackgroundTasks):
        return AssignmentNotifications(background, enabled=True)

    app.dependency_overrides[get_assignment_notifications] = enabled
    yield publisher
    app.dependency_overrides.pop(get_assignment_notifications, None)


async def create_task(client, seed_data, *, assigned=True):
    values = {"title": "Prepare release"}
    if assigned:
        values["assignee_id"] = seed_data["assignee_id"]
    response = await client.post(
        f"/api/v1/projects/{seed_data['project_id']}/tasks", json=values
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_assigned_task_queues_ids_after_transaction(
    client, seed_data, queued, session_factory, monkeypatch
):
    # A separate session can see the row before the background publisher runs.
    observed = []

    async def observe(task_id, assignee_id):
        async with session_factory() as session:
            task = await session.get(Task, task_id)
            observed.append((task.id, task.assignee_id))

    monkeypatch.setattr(notifications, "publish_assignment_email", observe)
    task = await create_task(client, seed_data)
    assert observed == [(task["id"], seed_data["assignee_id"])]


async def test_assignment_change_only_notifies_new_assignee(client, seed_data, queued):
    task = await create_task(client, seed_data, assigned=False)
    queued.assert_not_called()
    path = f"/api/v1/tasks/{task['id']}"
    response = await client.patch(path, json={"assignee_id": seed_data["assignee_id"]})
    assert response.status_code == 200
    queued.assert_called_once_with(task["id"], seed_data["assignee_id"])
    for changes in (
        {"assignee_id": seed_data["assignee_id"]},
        {"title": "Renamed"},
        {"assignee_id": None},
    ):
        assert (await client.patch(path, json=changes)).status_code == 200
    assert queued.call_count == 1
    assert (
        await client.patch(path, json={"assignee_id": seed_data["creator_id"]})
    ).status_code == 200
    assert queued.call_count == 2
    queued.assert_called_with(task["id"], seed_data["creator_id"])


async def test_disabled_notifications_do_not_publish(client, seed_data, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(notifications, "publish_assignment_email", publish)
    await create_task(client, seed_data)
    publish.assert_not_called()


async def test_failed_commit_does_not_queue_email(
    client, seed_data, queued, monkeypatch
):
    task = await create_task(client, seed_data, assigned=False)
    original = TaskRepository.update

    async def fail_after_update(repository, item, values):
        updated = await original(repository, item, values)
        await repository.session.execute(
            text("INSERT INTO task_labels (task_id, label_id) VALUES (:id, -1)"),
            {"id": updated.id},
        )
        return updated

    monkeypatch.setattr(TaskRepository, "update", fail_after_update)
    response = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee_id": seed_data["assignee_id"]}
    )
    assert response.status_code == 409
    queued.assert_not_called()
    assert (await client.get(f"/api/v1/tasks/{task['id']}")).json()[
        "assignee_id"
    ] is None


async def test_invalid_or_forbidden_assignment_does_not_queue(
    client, seed_data, roles, queued
):
    task = await create_task(client, seed_data, assigned=False)
    for role, expected in (("viewer", 403), ("outsider", 404)):
        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"assignee_id": seed_data["assignee_id"]},
            headers=roles[role]["headers"],
        )
        assert response.status_code == expected
    response = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee_id": roles["viewer"]["id"]}
    )
    assert response.status_code == 422
    queued.assert_not_called()


async def test_broker_failure_keeps_committed_task_and_hides_error_details(
    client, seed_data, queued, monkeypatch, caplog
):
    # Restore the real publisher; the dependency remains enabled.
    monkeypatch.setattr(notifications, "publish_assignment_email", REAL_PUBLISHER)
    apply = Mock(side_effect=OperationalError("private-broker-password"))
    monkeypatch.setattr(jobs.send_assignment_email, "apply_async", apply)
    task = await create_task(client, seed_data)
    apply.assert_called_once_with(
        args=[task["id"], seed_data["assignee_id"]],
        retry=False,
        expires=get_settings().assignment_email_expires_seconds,
    )
    assert (await client.get(f"/api/v1/tasks/{task['id']}")).status_code == 200
    assert "could not be queued" in caplog.text
    assert "private-broker-password" not in caplog.text


@pytest.fixture
def worker_session(session_factory, monkeypatch):
    @asynccontextmanager
    async def local_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(jobs, "job_session", local_session)


async def test_worker_loads_current_recipient(client, seed_data, worker_session):
    task = await create_task(client, seed_data)
    assert await jobs.assignment_details(task["id"], seed_data["assignee_id"]) == (
        "assignee@example.test",
        "Prepare release",
    )


@pytest.mark.parametrize(
    "change", ["delete", "unassign", "reassign", "inactive", "remove_member", "viewer"]
)
async def test_worker_skips_stale_or_ineligible_assignment(
    client, seed_data, worker_session, session_factory, change
):
    task = await create_task(client, seed_data)
    async with session_factory() as session:
        async with session.begin():
            item = await session.get(Task, task["id"])
            if change == "delete":
                await session.delete(item)
            elif change in ("unassign", "reassign"):
                item.assignee_id = (
                    None if change == "unassign" else seed_data["creator_id"]
                )
            elif change == "inactive":
                user = await session.get(User, seed_data["assignee_id"])
                user.is_active = False
            else:
                member = await session.get(
                    WorkspaceMember,
                    (seed_data["workspace_id"], seed_data["assignee_id"]),
                )
                if change == "remove_member":
                    await session.delete(member)
                else:
                    member.role = WorkspaceRole.VIEWER
    assert await jobs.assignment_details(task["id"], seed_data["assignee_id"]) is None


@pytest.fixture
def smtp_sink(monkeypatch, request):
    messages = Queue()

    class Handler:
        attempts = 0

        async def handle_RCPT(self, server, session, envelope, address, options):
            self.attempts += 1
            rejection = getattr(request, "param", None)
            if rejection and self.attempts == 1:
                return f"{rejection} Greylisted"
            envelope.rcpt_tos.append(address)
            return "250 OK"

        async def handle_DATA(self, server, session, envelope):
            messages.put(envelope)
            return "250 Message accepted"

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    controller = Controller(Handler(), hostname="127.0.0.1", port=port)
    controller.start()
    settings = get_settings().model_copy(
        update={
            "assignment_email_enabled": True,
            "smtp_host": "127.0.0.1",
            "smtp_port": port,
            "smtp_security": "none",
            "smtp_username": None,
            "smtp_password": None,
        }
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    try:
        yield messages
    finally:
        controller.stop()


def test_email_job_delivers_to_loopback_smtp(smtp_sink, monkeypatch):
    details = AsyncMock(return_value=("member@example.test", "Release <v2>"))
    monkeypatch.setattr(jobs, "assignment_details", details)
    result = jobs.send_assignment_email.apply(args=[42, 7], throw=True)
    assert result.result is True
    details.assert_awaited_once_with(42, 7)
    envelope = smtp_sink.get(timeout=2)
    assert envelope.rcpt_tos == ["member@example.test"]
    message = BytesParser(policy=policy.default).parsebytes(envelope.content)
    assert message["Subject"] == "TaskHub assignment #42"
    assert "Release <v2>" in message.get_content()
    assert message["Message-ID"] == f"<assignment-{result.id}@taskhub.local>"


def test_email_job_does_nothing_when_disabled(monkeypatch):
    details = AsyncMock()
    monkeypatch.setattr(jobs, "assignment_details", details)
    assert jobs.send_assignment_email.apply(args=[42, 7], throw=True).result is False
    details.assert_not_called()


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_authenticated_smtp_verifies_tls_before_login(monkeypatch, security):

    settings = get_settings().model_copy(
        update={
            "smtp_security": security,
            "smtp_username": "smtp-user",
            "smtp_password": SecretStr("private-test-password"),
        }
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    connection = Mock()
    smtp = Mock()
    smtp.return_value.__enter__ = Mock(return_value=connection)
    smtp.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(smtplib, "SMTP_SSL" if security == "ssl" else "SMTP", smtp)
    jobs.deliver_assignment("member@example.test", "Task", 42, "job-id")
    context = (
        smtp.call_args.kwargs["context"]
        if security == "ssl"
        else connection.starttls.call_args.kwargs["context"]
    )
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    connection.login.assert_called_once_with("smtp-user", "private-test-password")
    if security == "starttls":
        assert [call[0] for call in connection.mock_calls] == [
            "starttls",
            "login",
            "send_message",
        ]


def test_smtp_failure_is_retryable_and_does_not_leak_recipient(smtp_sink, monkeypatch):
    monkeypatch.setattr(
        jobs,
        "assignment_details",
        AsyncMock(return_value=("private@example.test", "Private")),
    )
    monkeypatch.setattr(
        smtplib.SMTP,
        "send_message",
        Mock(side_effect=smtplib.SMTPServerDisconnected("private@example.test")),
    )
    # Celery performs the retries in eager mode; stop after the configured bound.
    delivery = jobs.send_assignment_email.apply(args=[42, 7])
    assert delivery.failed()
    assert isinstance(delivery.result, jobs.EmailDeliveryError)
    assert str(delivery.result) == "SMTP delivery failed"
    assert smtplib.SMTP.send_message.call_count == get_settings().job_max_retries + 1


@pytest.mark.parametrize(
    "values",
    [
        {"smtp_username": "user"},
        {"smtp_password": "secret"},
        {"smtp_username": "user", "smtp_password": "secret", "smtp_security": "none"},
        {"refresh_cleanup_batch_size": 0},
        {"job_max_retries": -1},
    ],
)
def test_background_settings_reject_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=TEST_DATABASE_URL,
            jwt_secret_key="x" * 64,
            **values,
        )


def test_celery_uses_json_no_results_and_bounded_periodic_cleanup():
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_ignore_result is True
    schedule = celery_app.conf.beat_schedule["cleanup-expired-refresh-tokens"]
    assert schedule["task"] == "taskhub.cleanup_expired_refresh_tokens"
    assert schedule["schedule"] == get_settings().refresh_cleanup_interval_seconds
    assert schedule["options"]["expires"] == schedule["schedule"]


def token(user_id, expires_at, *, revoked=False):
    return RefreshToken(
        user_id=user_id,
        jti=uuid.uuid4().hex,
        expires_at=expires_at,
        revoked_at=datetime.now(UTC) if revoked else None,
    )


async def test_cleanup_batches_are_idempotent_and_preserve_unexpired_revoked_tokens(
    seed_data, session_factory, worker_session, monkeypatch
):
    now = datetime.now(UTC)
    rows = [
        token(seed_data["creator_id"], now - timedelta(days=1), revoked=revoked)
        for revoked in (False, True, False)
    ]
    retained = [
        token(seed_data["creator_id"], now + timedelta(days=1), revoked=revoked)
        for revoked in (False, True)
    ]
    async with session_factory() as session, session.begin():
        session.add_all(rows + retained)
        await session.flush()
        retained_ids = {row.id for row in retained}
    settings = get_settings().model_copy(update={"refresh_cleanup_batch_size": 2})
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    assert await jobs.cleanup_expired_tokens() == 3
    assert await jobs.cleanup_expired_tokens() == 0
    assert await jobs.cleanup_expired_tokens() == 0
    async with session_factory() as session:
        assert (
            set((await session.scalars(select(RefreshToken.id))).all()) == retained_ids
        )


async def test_cleanup_includes_expiry_boundary_and_rolls_back_on_failure(
    seed_data, session_factory
):
    cutoff = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        row = token(seed_data["creator_id"], cutoff)
        session.add(row)
        await session.flush()
        row_id = row.id
    with pytest.raises(RuntimeError):
        async with session_factory() as session, session.begin():
            assert (
                await RefreshTokenRepository(session).delete_expired_batch(
                    cutoff, limit=1
                )
                == 1
            )
            raise RuntimeError("Roll back cleanup")
    async with session_factory() as session:
        assert await session.get(RefreshToken, row_id) is not None


async def test_overlapping_cleanup_workers_skip_locked_rows(migrated_database):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = None
    try:
        async with factory() as session, session.begin():
            user = User(
                email=f"cleanup-{uuid.uuid4().hex}@example.test",
                full_name="Cleanup",
                hashed_password="TEST_LOGIN_DISABLED",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            session.add_all(
                [
                    token(user_id, datetime.now(UTC) - timedelta(days=1))
                    for _ in range(3)
                ]
            )
        async with factory() as first, factory() as second:
            async with first.begin(), second.begin():
                assert (
                    await RefreshTokenRepository(first).delete_expired_batch(
                        datetime.now(UTC), limit=1
                    )
                    == 1
                )
                # First transaction still holds its row lock. Second must not wait.
                count = await asyncio.wait_for(
                    RefreshTokenRepository(second).delete_expired_batch(
                        datetime.now(UTC), limit=10
                    ),
                    timeout=3,
                )
                assert count == 2
        async with factory() as session:
            assert (
                await session.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            ).all() == []
    finally:
        try:
            async with factory() as session, session.begin():
                if user_id is not None:
                    await session.execute(delete(User).where(User.id == user_id))
        finally:
            await engine.dispose()


@pytest.mark.parametrize(
    "error",
    [
        OSError("private-quit-error"),
        smtplib.SMTPResponseException(451, b"private-quit-error"),
    ],
)
def test_quit_failure_after_acceptance_does_not_retry(
    smtp_sink, monkeypatch, caplog, error
):
    caplog.set_level("INFO", logger="app.jobs")
    connection = Mock()
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value = connection
    smtp.return_value.__exit__.side_effect = error
    monkeypatch.setattr(smtplib, "SMTP", smtp)
    details = AsyncMock(return_value=("private@example.test", "Private title"))
    monkeypatch.setattr(jobs, "assignment_details", details)
    assert jobs.send_assignment_email.apply(args=[42, 7], throw=True).result is True
    connection.send_message.assert_called_once()
    assert details.await_count == 1
    assert type(error).__name__ in caplog.text
    assert "private-quit-error" not in caplog.text
    assert "SMTP QUIT failed after delivery" in caplog.text
    assert "SMTP delivery failed" not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPAuthenticationError(535, b"private-auth"),
        smtplib.SMTPConnectError(554, b"private-connect"),
        smtplib.SMTPDataError(550, b"private-data"),
        ssl.SSLCertVerificationError(1, "private-certificate"),
        smtplib.SMTPRecipientsRefused(
            {"private@example.test": (550, b"private-recipient")}
        ),
    ],
)
def test_permanent_smtp_rejection_is_sanitized_and_not_retried(
    smtp_sink, monkeypatch, caplog, error
):
    details = AsyncMock(return_value=("private@example.test", "Private title"))
    monkeypatch.setattr(jobs, "assignment_details", details)
    monkeypatch.setattr(smtplib.SMTP, "send_message", Mock(side_effect=error))
    result = jobs.send_assignment_email.apply(args=[42, 7])
    assert result.failed()
    assert isinstance(result.result, jobs.EmailDeliveryPermanentError)
    assert details.await_count == 1
    assert type(error).__name__ in caplog.text
    assert "private-auth" not in caplog.text
    assert "private-recipient" not in caplog.text
    assert "private@example.test" not in caplog.text


async def test_cleanup_stops_at_its_time_budget(worker_session, monkeypatch):
    settings = get_settings().model_copy(
        update={"refresh_cleanup_budget_seconds": 0.01}
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)

    async def blocked(*args, **kwargs):
        await asyncio.sleep(1)
        return settings.refresh_cleanup_batch_size

    monkeypatch.setattr(RefreshTokenRepository, "delete_expired_batch", blocked)
    assert await jobs.cleanup_expired_tokens() == 0


@pytest.mark.parametrize(
    "error_type,retryable",
    [
        (DBOperationalError, True),
        (InterfaceError, True),
        (ProgrammingError, False),
        (IntegrityError, False),
    ],
)
def test_email_retries_only_transient_database_errors(
    monkeypatch, error_type, retryable
):
    settings = get_settings().model_copy(update={"assignment_email_enabled": True})
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    details = AsyncMock(
        side_effect=error_type(None, None, Exception("database failure"))
    )
    monkeypatch.setattr(jobs, "assignment_details", details)
    result = jobs.send_assignment_email.apply(args=[42, 7])
    assert result.failed()
    assert isinstance(result.result, error_type)
    assert details.await_count == (settings.job_max_retries + 1 if retryable else 1)


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPRecipientsRefused(
            {"private@example.test": (451, b"private-greylist")}
        ),
        smtplib.SMTPDataError(421, b"private-busy"),
        smtplib.SMTPSenderRefused(452, b"private-full", "private@example.test"),
        smtplib.SMTPConnectError(421, b"private-connect"),
    ],
)
def test_temporary_smtp_response_is_retried(smtp_sink, monkeypatch, caplog, error):
    details = AsyncMock(return_value=("private@example.test", "Private title"))
    monkeypatch.setattr(jobs, "assignment_details", details)
    monkeypatch.setattr(smtplib.SMTP, "send_message", Mock(side_effect=error))
    result = jobs.send_assignment_email.apply(args=[42, 7])
    assert result.failed()
    assert isinstance(result.result, jobs.EmailDeliveryError)
    assert details.await_count == get_settings().job_max_retries + 1
    assert type(error).__name__ in caplog.text
    assert "private@example.test" not in caplog.text
    assert "private-greylist" not in caplog.text


@pytest.mark.parametrize("smtp_sink", [451], indirect=True)
def test_greylisted_rcpt_retries_and_delivers_once(smtp_sink, monkeypatch):
    details = AsyncMock(return_value=("member@example.test", "Greylisting recovery"))
    monkeypatch.setattr(jobs, "assignment_details", details)
    result = jobs.send_assignment_email.apply(args=[42, 7])
    assert result.result is True
    assert details.await_count == 2
    envelope = smtp_sink.get(timeout=2)
    assert envelope.rcpt_tos == ["member@example.test"]
    assert smtp_sink.empty()


@pytest.mark.parametrize("committed_batches", [1, 2])
async def test_cleanup_budget_keeps_prior_commits_and_rolls_back_current_batch(
    committed_batches, migrated_database, monkeypatch
):
    # Independent PostgreSQL connections and real commits, not savepoints.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = None
    batch_size = 2
    settings = get_settings().model_copy(
        update={
            "refresh_cleanup_budget_seconds": 1,
            "refresh_cleanup_batch_size": batch_size,
        }
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)

    @asynccontextmanager
    async def local_session():
        async with factory() as session:
            yield session

    monkeypatch.setattr(jobs, "job_session", local_session)
    original = RefreshTokenRepository.delete_expired_batch
    calls = 0

    async def delete_then_block(repository, cutoff, *, limit):
        nonlocal calls
        count = await original(repository, cutoff, limit=limit)
        calls += 1
        if calls > committed_batches:
            # Delete in the next batch before blocking: its transaction must
            # roll back on cancellation, while prior commits remain durable.
            await asyncio.Event().wait()
        return count

    try:
        now = datetime.now(UTC)
        async with factory() as session, session.begin():
            user = User(
                email=f"cleanup-budget-{uuid.uuid4().hex}@example.test",
                full_name="Cleanup budget",
                hashed_password="TEST_LOGIN_DISABLED",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            expired = [
                token(user_id, now - timedelta(days=1))
                for _ in range(committed_batches * batch_size + 1)
            ]
            retained = token(user_id, now + timedelta(days=1), revoked=True)
            session.add_all([*expired, retained])
            await session.flush()
            last_expired_id, retained_id = expired[-1].id, retained.id
        monkeypatch.setattr(
            RefreshTokenRepository, "delete_expired_batch", delete_then_block
        )
        assert await jobs.cleanup_expired_tokens() == committed_batches * batch_size
        assert calls == committed_batches + 1
        async with factory() as session:
            remaining = set(
                (
                    await session.scalars(
                        select(RefreshToken.id).where(RefreshToken.user_id == user_id)
                    )
                ).all()
            )
            assert remaining == {last_expired_id, retained_id}
    finally:
        try:
            async with factory() as session, session.begin():
                if user_id is not None:
                    await session.execute(delete(User).where(User.id == user_id))
        finally:
            await engine.dispose()
