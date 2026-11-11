# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import AuthServiceDep
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth_service import (
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    InvalidRefreshToken,
)

router = APIRouter()

BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(data: RegisterRequest, service: AuthServiceDep):
    try:
        return await service.register(data)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, service: AuthServiceDep):
    try:
        return await service.login(data)
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers=BEARER_HEADERS,
        ) from exc
    except InactiveUser as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, service: AuthServiceDep):
    try:
        return await service.refresh(data.refresh_token)
    except InvalidRefreshToken as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers=BEARER_HEADERS,
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshTokenRequest, service: AuthServiceDep):
    try:
        await service.logout(data.refresh_token)
    except InvalidRefreshToken as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers=BEARER_HEADERS,
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
