"""OpenAPI `responses` dùng chung cho các endpoint."""

from typing import Any

from fastapi import status

from app.core import messages
from app.schemas.error import ErrorResponse

VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": "Invalid request data or reference",
    },
}

UNAUTHORIZED_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": messages.AUTHENTICATION_REQUIRED,
        "headers": {"WWW-Authenticate": {"schema": {"type": "string"}}},
    },
}

FORBIDDEN_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ErrorResponse,
        "description": messages.PERMISSION_DENIED,
    },
}

AUTH_RESPONSES = {**UNAUTHORIZED_RESPONSES, **FORBIDDEN_RESPONSES}


def not_found_response(*resources: str) -> dict[int | str, dict[str, Any]]:
    """Một mã 404 chỉ có một mô tả, nên gộp mọi resource có thể không tìm thấy."""
    return {
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": " / ".join(
                messages.RESOURCE_NOT_FOUND.format(resource=resource)
                for resource in resources
            ),
        },
    }


def conflict_response(description: str) -> dict[int | str, dict[str, Any]]:
    return {
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": description,
        },
    }
