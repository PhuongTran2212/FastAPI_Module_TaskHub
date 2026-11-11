import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.exceptions import AppException
from app.db.session import engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("TaskHub starting...")

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        logger.info("Database connection ready")

        yield
    finally:
        await engine.dispose()
        logger.info("TaskHub shutting down...")


app = FastAPI(
    title="TaskHub API",
    version="0.3.0",
    description="Task Management API",
    lifespan=lifespan,
)


@app.exception_handler(AppException)
async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}