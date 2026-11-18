from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, ProjectServiceDep, WorkspaceServiceDep
from app.api.pagination import PaginationDep
from app.api.responses import (
    AUTH_RESPONSES,
    UNAUTHORIZED_RESPONSES,
    VALIDATION_RESPONSES,
    conflict_response,
    not_found_response,
)
from app.core import messages
from app.core.enums import ProjectStatus
from app.schemas.project import ProjectCreate, ProjectPage, ProjectRead
from app.schemas.workspace import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    WorkspaceCreate,
    WorkspacePage,
    WorkspaceRead,
    WorkspaceUpdate,
)

router = APIRouter()

WORKSPACE_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Workspace"),
}
MEMBER_RESPONSES = {
    **WORKSPACE_RESPONSES,
    **not_found_response("Workspace", "Member"),
    **conflict_response(messages.OWNER_MEMBERSHIP_LOCKED),
}


# ---------- Workspace ----------
@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace (the creator becomes OWNER)",
    responses={**VALIDATION_RESPONSES, **UNAUTHORIZED_RESPONSES},
)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> WorkspaceRead:
    return await service.create(current_user, data)


@router.get(
    "",
    response_model=WorkspacePage,
    summary="List workspaces I belong to (ADMIN: all)",
    responses={**VALIDATION_RESPONSES, **AUTH_RESPONSES},
)
async def list_workspaces(
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
    pagination: PaginationDep,
) -> WorkspacePage:
    return await service.list_for_user(
        current_user, page=pagination.page, limit=pagination.limit
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Get a workspace (any member)",
    responses=WORKSPACE_RESPONSES,
)
async def get_workspace(
    workspace_id: int,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> WorkspaceRead:
    return await service.get(current_user, workspace_id)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Rename a workspace (OWNER)",
    responses=WORKSPACE_RESPONSES,
)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> WorkspaceRead:
    return await service.update(current_user, workspace_id, data)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a workspace and everything in it (OWNER)",
    responses=WORKSPACE_RESPONSES,
)
async def delete_workspace(
    workspace_id: int,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> Response:
    await service.delete(current_user, workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Members ----------
@router.get(
    "/{workspace_id}/members",
    response_model=list[MemberRead],
    summary="List members (any member)",
    responses=WORKSPACE_RESPONSES,
)
async def list_members(
    workspace_id: int,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> list[MemberRead]:
    return await service.list_members(current_user, workspace_id)


@router.post(
    "/{workspace_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a registered user by email (OWNER)",
    responses={
        **WORKSPACE_RESPONSES,
        **not_found_response("Workspace", "User"),
        **conflict_response(messages.MEMBER_ALREADY_EXISTS),
    },
)
async def add_member(
    workspace_id: int,
    data: MemberCreate,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> MemberRead:
    return await service.add_member(current_user, workspace_id, data)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=MemberRead,
    summary="Change a member's role (OWNER)",
    responses=MEMBER_RESPONSES,
)
async def update_member(
    workspace_id: int,
    user_id: int,
    data: MemberUpdate,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> MemberRead:
    return await service.update_member(current_user, workspace_id, user_id, data)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a member and unassign their tasks (OWNER)",
    responses=MEMBER_RESPONSES,
)
async def remove_member(
    workspace_id: int,
    user_id: int,
    current_user: CurrentUser,
    service: WorkspaceServiceDep,
) -> Response:
    await service.remove_member(current_user, workspace_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Projects ----------
@router.post(
    "/{workspace_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project in a workspace (EDITOR)",
    responses=WORKSPACE_RESPONSES,
)
async def create_project(
    workspace_id: int,
    data: ProjectCreate,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    return await service.create(current_user, workspace_id, data)


@router.get(
    "/{workspace_id}/projects",
    response_model=ProjectPage,
    summary="List projects of a workspace (any member)",
    responses=WORKSPACE_RESPONSES,
)
async def list_projects(
    workspace_id: int,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    pagination: PaginationDep,
    status: ProjectStatus | None = None,
) -> ProjectPage:
    return await service.list_for_workspace(
        current_user,
        workspace_id,
        page=pagination.page,
        limit=pagination.limit,
        status=status,
    )
