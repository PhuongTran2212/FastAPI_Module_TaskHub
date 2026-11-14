# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Response, status

from app.api.deps import AuthServiceDep
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(data: RegisterRequest, service: AuthServiceDep):
    return await service.register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, service: AuthServiceDep):
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, service: AuthServiceDep):
    return await service.refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshTokenRequest, service: AuthServiceDep):
    await service.logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
