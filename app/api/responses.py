"""OpenAPI `responses` dùng chung cho các endpoint."""

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
