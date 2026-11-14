import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.constants import TASK_TITLE_MAX_LENGTH
from app.models import Comment, Label, Project, Task, User, Workspace


async def test_migrated_constraint_names_and_delete_actions(db_connection):
    def inspect_constraints(connection):
        inspector = inspect(connection)
        return (
            {
                table: inspector.get_foreign_keys(table)
                for table in ("tasks", "workspaces", "comments")
            },
            inspector.get_unique_constraints("labels"),
            inspector.get_columns("tasks"),
        )

    foreign_keys, unique_constraints, columns = await db_connection.run_sync(
        inspect_constraints
    )
    for table, column, action in (
        ("tasks", "assignee_id", "SET NULL"),
        ("tasks", "created_by", "RESTRICT"),
        ("workspaces", "owner_id", "RESTRICT"),
        ("comments", "author_id", "RESTRICT"),
    ):
        fk = next(
            item
            for item in foreign_keys[table]
            if item["constrained_columns"] == [column]
        )
        assert fk["options"]["ondelete"] == action
    assert any(
        item["name"] == "uq_labels_project_id_name"
        and item["column_names"] == ["project_id", "name"]
        for item in unique_constraints
    )
    assert (
        next(item for item in columns if item["name"] == "title")["type"].length
        == TASK_TITLE_MAX_LENGTH
    )


async def test_deleting_assignee_sets_task_assignee_to_null(session_factory, seed_data):
    async with session_factory() as session:
        async with session.begin():
            task = Task(
                title="Assigned",
                project_id=seed_data["project_id"],
                created_by=seed_data["creator_id"],
                assignee_id=seed_data["assignee_id"],
            )
            session.add(task)
            await session.flush()
            task_id = task.id
    async with session_factory() as session:
        async with session.begin():
            await session.delete(await session.get(User, seed_data["assignee_id"]))
    async with session_factory() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        assert task.assignee_id is None


@pytest.mark.parametrize("reference", ["owner", "creator", "author"])
async def test_restrict_prevents_deleting_referenced_user(
    session_factory, seed_data, reference
):
    async with session_factory() as session:
        async with session.begin():
            user = User(
                email="restricted@example.test",
                full_name="Referenced user",
                hashed_password="TEST_LOGIN_DISABLED",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            if reference == "owner":
                session.add(Workspace(name="Restricted", owner_id=user_id))
            else:
                task = Task(
                    title="Task",
                    project_id=seed_data["project_id"],
                    created_by=user_id
                    if reference == "creator"
                    else seed_data["creator_id"],
                )
                session.add(task)
                await session.flush()
                if reference == "author":
                    session.add(
                        Comment(task_id=task.id, author_id=user_id, content="Comment")
                    )

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            async with session.begin():
                await session.delete(await session.get(User, user_id))
                await session.flush()
    async with session_factory() as session:
        assert await session.get(User, user_id) is not None


async def test_label_unique_within_project(session_factory, seed_data):
    async with session_factory() as session:
        async with session.begin():
            session.add_all(
                [
                    Label(project_id=seed_data["project_id"], name="Bug"),
                    Label(project_id=seed_data["other_project_id"], name="Bug"),
                ]
            )
    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            async with session.begin():
                session.add(Label(project_id=seed_data["project_id"], name="Bug"))
                await session.flush()


async def test_project_delete_cascades_to_tasks_and_children(
    session_factory, seed_data
):
    async with session_factory() as session:
        async with session.begin():
            task = Task(
                title="Cascade",
                project_id=seed_data["project_id"],
                created_by=seed_data["creator_id"],
            )
            label = Label(project_id=seed_data["project_id"], name="Bug")
            session.add_all([task, label])
            await session.flush()
            comment = Comment(
                task_id=task.id, author_id=seed_data["creator_id"], content="Comment"
            )
            session.add(comment)
            await session.flush()
            ids = task.id, label.id, comment.id
            await session.execute(
                text(
                    "INSERT INTO task_labels (task_id, label_id) VALUES (:task, :label)"
                ),
                {"task": task.id, "label": label.id},
            )
    async with session_factory() as session:
        async with session.begin():
            await session.delete(await session.get(Project, seed_data["project_id"]))
    async with session_factory() as session:
        for model, item_id in zip((Task, Label, Comment), ids):
            assert await session.get(model, item_id) is None
        assert (
            await session.scalar(
                text("SELECT count(*) FROM task_labels WHERE task_id = :id"),
                {"id": ids[0]},
            )
            == 0
        )
