from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.task_service import TaskService


SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


TaskRepoDep = Annotated[
    TaskRepository,
    Depends(get_task_repository),
]

ProjectRepoDep = Annotated[
    ProjectRepository,
    Depends(get_project_repository),
]

UserRepoDep = Annotated[
    UserRepository,
    Depends(get_user_repository),
]


def get_task_service(
    repo: TaskRepoDep,
    projects: ProjectRepoDep,
    users: UserRepoDep,
) -> TaskService:
    return TaskService(
        repo=repo,
        projects=projects,
        users=users,
    )


TaskServiceDep = Annotated[
    TaskService,
    Depends(get_task_service),
]