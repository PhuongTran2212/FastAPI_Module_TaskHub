from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import DateTime, String, event, func, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models import Task, WorkspaceMember
from app.repositories.base import BaseRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskRead, TaskUpdate
from scripts import smoke_background


async def test_task_writes_return_defaults_without_followup_selects(
    seed_data, session_factory, db_connection
):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        async with session_factory() as session, session.begin():
            repository = TaskRepository(session)
            task = await repository.create(
                {
                    "project_id": seed_data["project_id"],
                    "created_by": seed_data["creator_id"],
                    "title": "Write budget",
                }
            )
            created = TaskRead.model_validate(task)
            assert created.id > 0
            assert created.created_at.tzinfo is not None
            assert created.status == "TODO"
            assert created.priority == "MEDIUM"
            updated = await repository.update(task, {"title": "Updated budget"})
            result = TaskRead.model_validate(updated)
        # A write already flushes RETURNING/defaults. Rereading the full row
        # adds a network round trip without improving this API's response.
        assert not any(
            query.lstrip().upper().startswith("SELECT") for query in statements
        )
        assert (
            sum(query.lstrip().upper().startswith("INSERT") for query in statements)
            == 1
        )
        assert (
            sum(query.lstrip().upper().startswith("UPDATE") for query in statements)
            == 3
        )
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)

    async with session_factory() as session:
        stored = await session.get(Task, result.id)
        assert stored is not None
        assert TaskRead.model_validate(stored) == result


async def test_generic_pagination_keeps_composite_primary_key_order(
    seed_data, session_factory
):
    async with session_factory() as session:
        repository = BaseRepository(session, WorkspaceMember)
        first, total = await repository.list_page(page=1, limit=1)
        second, second_total = await repository.list_page(page=2, limit=1)
        expected = sorted([seed_data["creator_id"], seed_data["assignee_id"]])
        assert total == second_total == 2
        assert [first[0].user_id, second[0].user_id] == expected
        assert [member.user_id for member in await repository.list(limit=2)] == expected


async def test_overdue_task_can_still_be_read_and_updated(
    client, seed_data, session_factory
):
    # Validation applies to incoming dates, not old stored dates in a read model.
    yesterday = date.today() - timedelta(days=1)
    async with session_factory() as session, session.begin():
        task = await TaskRepository(session).create(
            {
                "project_id": seed_data["project_id"],
                "created_by": seed_data["creator_id"],
                "title": "Already overdue",
                "due_date": yesterday,
            }
        )
        task_id = task.id
    response = await client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["due_date"] == yesterday.isoformat()
    response = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "DONE"})
    assert response.status_code == 200
    assert response.json()["due_date"] == yesterday.isoformat()
    assert response.json()["status"] == "DONE"


def test_smoke_cleans_up_its_user_even_when_login_fails(monkeypatch):
    def api(method, url, data=None, access_token=None):
        if url.endswith("/register"):
            return {"id": 42}
        raise RuntimeError("Login unavailable")

    cleanup = Mock(return_value="")
    monkeypatch.setattr(smoke_background, "request", api)
    monkeypatch.setattr(smoke_background, "compose_python", cleanup)
    with pytest.raises(RuntimeError, match="Login unavailable"):
        smoke_background.main()
    cleanup.assert_called_once()
    assert "User.id == 42" in cleanup.call_args.args[0]


def test_omitted_patch_due_date_stays_omitted_and_explicit_null_can_clear():
    assert TaskUpdate(status="DONE").model_dump(exclude_unset=True) == {
        "status": "DONE"
    }
    assert TaskUpdate(due_date=None).model_dump(exclude_unset=True) == {
        "due_date": None
    }


async def test_server_generated_update_default_is_available_without_implicit_io(
    session_factory, db_connection
):



    class UpdatedItem(Base):
        __tablename__ = "review_generated_defaults"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String(50))
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        )

    try:
        await db_connection.run_sync(UpdatedItem.__table__.create)
        async with session_factory() as session, session.begin():
            item = UpdatedItem(name="before")
            session.add(item)
            await session.flush()
            item.name = "after"
            await session.flush()
            assert "updated_at" not in inspect(item).expired_attributes
            assert item.updated_at.tzinfo is not None
    finally:
        Base.metadata.remove(UpdatedItem.__table__)
