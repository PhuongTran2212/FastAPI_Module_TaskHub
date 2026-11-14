import asyncio

from sqlalchemy import select

from app.core.enums import WorkspaceRole
from app.db.session import SessionFactory, engine
from app.models import Project, User, Workspace, WorkspaceMember


async def main() -> None:
    try:
        async with SessionFactory() as session:
            async with session.begin():
                user = await session.scalar(
                    select(User).where(User.email == "day2@example.com")
                )

                if user is None:
                    user = User(
                        email="day2@example.com",
                        full_name="Day 2 Demo",
                        hashed_password="DAY2_DEMO_LOGIN_DISABLED",
                        is_active=False,
                    )
                    session.add(user)
                    await session.flush()

                workspace = await session.scalar(
                    select(Workspace)
                    .where(
                        Workspace.owner_id == user.id,
                        Workspace.name == "Day 2 Workspace",
                    )
                    .order_by(Workspace.id)
                )

                if workspace is None:
                    workspace = Workspace(
                        name="Day 2 Workspace",
                        owner_id=user.id,
                    )
                    session.add(workspace)
                    await session.flush()

                member = await session.get(
                    WorkspaceMember,
                    (workspace.id, user.id),
                )

                if member is None:
                    session.add(
                        WorkspaceMember(
                            workspace_id=workspace.id,
                            user_id=user.id,
                            role=WorkspaceRole.OWNER,
                        )
                    )

                project = await session.scalar(
                    select(Project)
                    .where(
                        Project.workspace_id == workspace.id,
                        Project.name == "Day 2 Project",
                    )
                    .order_by(Project.id)
                )

                if project is None:
                    project = Project(
                        workspace_id=workspace.id,
                        name="Day 2 Project",
                    )
                    session.add(project)
                    await session.flush()

                user_id = user.id
                workspace_id = workspace.id
                project_id = project.id

            print(
                f"created_by={user_id}, "
                f"workspace_id={workspace_id}, "
                f"project_id={project_id}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
