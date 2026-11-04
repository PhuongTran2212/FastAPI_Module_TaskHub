from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: sau này khởi tạo DB engine, Redis connection ở đây
    print("TaskHub starting...")
    yield
    # Shutdown: đóng connection
    print("TaskHub shutting down...")


app = FastAPI(
    title="TaskHub API",
    version="0.1.0",
    description="Task Management API",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}