# app/api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, UserServiceDep, require_admin
from app.schemas.user import ChangePasswordRequest, UserRead, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_me(current_user: CurrentUser):
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
):
    return await service.update_profile(current_user, data)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    service: UserServiceDep,
):
    await service.change_password(current_user, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=list[UserRead],
    dependencies=[Depends(require_admin)],
)
async def list_users(
    service: UserServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    return await service.list_users(page=page, limit=limit)
