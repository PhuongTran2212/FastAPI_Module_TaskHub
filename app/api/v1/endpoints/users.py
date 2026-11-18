# app/api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, UserServiceDep, require_admin
from app.api.pagination import PaginationDep
from app.api.responses import AUTH_RESPONSES, VALIDATION_RESPONSES
from app.core import messages
from app.schemas.error import ErrorResponse
from app.schemas.user import ChangePasswordRequest, UserPage, UserRead, UserUpdate

router = APIRouter()


@router.get(
    "/me",
    response_model=UserRead,
    summary="Read my profile",
    responses=AUTH_RESPONSES,
)
async def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update my profile",
    responses={**AUTH_RESPONSES, **VALIDATION_RESPONSES},
)
async def update_me(
    data: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> UserRead:
    return await service.update_profile(current_user, data)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Change my password",
    responses={
        **AUTH_RESPONSES,
        **VALIDATION_RESPONSES,
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": messages.INCORRECT_CURRENT_PASSWORD,
        },
    },
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> Response:
    await service.change_password(current_user, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=UserPage,
    dependencies=[Depends(require_admin)],
    summary="List users (admin only)",
    responses={**AUTH_RESPONSES, **VALIDATION_RESPONSES},
)
async def list_users(service: UserServiceDep, pagination: PaginationDep) -> UserPage:
    return await service.list_users(page=pagination.page, limit=pagination.limit)
