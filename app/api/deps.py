# app/api/deps.py
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TokenType, UserRole
from app.core.exceptions import (
    ForbiddenException,
    InactiveUser,
    TokenError,
    UnauthorizedException,
)
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.task_service import TaskService
from app.services.user_service import UserService

SessionDep = Annotated[AsyncSession, Depends(get_db)]

# auto_error=False để tự trả 401 thống nhất khi thiếu header
bearer_scheme = HTTPBearer(auto_error=False)


# ---------- Repositories ----------
def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepoDep = Annotated[
    RefreshTokenRepository,
    Depends(get_refresh_token_repository),
]
TaskRepoDep = Annotated[TaskRepository, Depends(get_task_repository)]
ProjectRepoDep = Annotated[ProjectRepository, Depends(get_project_repository)]


# ---------- Services ----------
def get_auth_service(
    users: UserRepoDep,
    refresh_tokens: RefreshTokenRepoDep,
) -> AuthService:
    return AuthService(users, refresh_tokens)


def get_user_service(
    users: UserRepoDep,
    refresh_tokens: RefreshTokenRepoDep,
) -> UserService:
    return UserService(users, refresh_tokens)


def get_task_service(
    repo: TaskRepoDep,
    projects: ProjectRepoDep,
    users: UserRepoDep,
) -> TaskService:
    return TaskService(repo=repo, projects=projects, users=users)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


# ---------- Auth ----------
async def get_current_user(
    users: UserRepoDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> User:
    if credentials is None:
        raise UnauthorizedException()

    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except TokenError as exc:
        raise UnauthorizedException() from exc

    # Đóng transaction ngay sau khi đọc → service phía sau mở begin() được
    async with users.session.begin():
        user = await users.get(payload.user_id)

    if user is None:
        raise UnauthorizedException()

    if not user.is_active:
        raise InactiveUser()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def role_checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise ForbiddenException()
        return current_user

    return role_checker


require_admin = require_roles(UserRole.ADMIN)
