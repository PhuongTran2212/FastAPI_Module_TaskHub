# app/api/v1/router.py
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1.endpoints import auth, tasks, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_current_user)],  # mọi route /tasks cần đăng nhập
)
