from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, ProjectServiceDep
from app.api.responses import (
    AUTH_RESPONSES,
    VALIDATION_RESPONSES,
    not_found_response,
)
from app.schemas.project import ProjectRead, ProjectUpdate

router = APIRouter()

PROJECT_RESPONSES = {
    **VALIDATION_RESPONSES,
    **AUTH_RESPONSES,
    **not_found_response("Project"),
}


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project (any member)",
    responses=PROJECT_RESPONSES,
)
async def get_project(
    project_id: int,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    return await service.get(current_user, project_id)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update or archive a project (EDITOR)",
    description=(
        'Send `{"status": "ARCHIVED"}` to archive and `{"status": "ACTIVE"}` to '
        "restore. Tasks of an archived project are read-only."
    ),
    responses=PROJECT_RESPONSES,
)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    return await service.update(current_user, project_id, data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a project and its tasks (OWNER)",
    responses=PROJECT_RESPONSES,
)
async def delete_project(
    project_id: int,
    current_user: CurrentUser,
    service: ProjectServiceDep,
) -> Response:
    await service.delete(current_user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
