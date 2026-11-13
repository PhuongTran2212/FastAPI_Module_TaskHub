from app.core import messages
from app.schemas.error import ErrorResponse

VALIDATION_RESPONSES = {422: {"description": "Invalid request data or reference"}}
UNAUTHORIZED_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": messages.AUTHENTICATION_REQUIRED,
        "headers": {"WWW-Authenticate": {"schema": {"type": "string"}}},
    },
}
FORBIDDEN_RESPONSES = {
    403: {"model": ErrorResponse, "description": messages.PERMISSION_DENIED}
}
AUTH_RESPONSES = {**UNAUTHORIZED_RESPONSES, **FORBIDDEN_RESPONSES}
