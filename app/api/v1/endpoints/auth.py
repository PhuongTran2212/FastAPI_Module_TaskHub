from fastapi import APIRouter, Response, status

from app.api.deps import AuthServiceDep
from app.api.responses import (
    AUTH_RESPONSES,
    UNAUTHORIZED_RESPONSES,
    VALIDATION_RESPONSES,
)
from app.core import messages
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.error import ErrorResponse
from app.schemas.user import UserRead

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an account",
    responses={
        **VALIDATION_RESPONSES,
        409: {"model": ErrorResponse, "description": messages.EMAIL_ALREADY_REGISTERED},
    },
)
async def register(data: RegisterRequest, service: AuthServiceDep) -> UserRead:
    return await service.register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    responses={**VALIDATION_RESPONSES, **AUTH_RESPONSES},
)
async def login(data: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.login(data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token",
    responses={**VALIDATION_RESPONSES, **UNAUTHORIZED_RESPONSES},
)
async def refresh(data: RefreshTokenRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.refresh(data.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Revoke a refresh token",
    responses={**VALIDATION_RESPONSES, **UNAUTHORIZED_RESPONSES},
)
async def logout(data: RefreshTokenRequest, service: AuthServiceDep) -> Response:
    await service.logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
