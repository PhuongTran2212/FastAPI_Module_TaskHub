from http import HTTPStatus

from app.core import messages
from app.core.constants import BEARER_HEADERS


class AppException(Exception):
    def __init__(
        self,
        detail: str,
        status_code: int = HTTPStatus.BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.headers = headers


class NotFoundException(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(
            detail=messages.RESOURCE_NOT_FOUND.format(resource=resource),
            status_code=HTTPStatus.NOT_FOUND,
        )


class UnprocessableException(AppException):
    """Dữ liệu đúng định dạng nhưng vi phạm quy tắc nghiệp vụ (422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


class ConflictException(AppException):
    def __init__(self, detail: str = messages.TASK_CONFLICT) -> None:
        super().__init__(detail=detail, status_code=HTTPStatus.CONFLICT)


class UnauthorizedException(AppException):
    """401 luôn kèm header WWW-Authenticate: Bearer."""

    def __init__(self, detail: str = messages.AUTHENTICATION_REQUIRED) -> None:
        super().__init__(
            detail=detail,
            status_code=HTTPStatus.UNAUTHORIZED,
            headers=BEARER_HEADERS.copy(),
        )


class ForbiddenException(AppException):
    def __init__(self, detail: str = messages.PERMISSION_DENIED) -> None:
        super().__init__(detail=detail, status_code=HTTPStatus.FORBIDDEN)


class TokenError(UnauthorizedException):
    pass


class EmailAlreadyRegistered(ConflictException):
    def __init__(self) -> None:
        super().__init__(messages.EMAIL_ALREADY_REGISTERED)


class InvalidCredentials(UnauthorizedException):
    def __init__(self) -> None:
        super().__init__(messages.INVALID_CREDENTIALS)


class InactiveUser(ForbiddenException):
    def __init__(self) -> None:
        super().__init__(messages.ACCOUNT_DISABLED)


class InvalidRefreshToken(UnauthorizedException):
    def __init__(self, detail: str = messages.INVALID_REFRESH_TOKEN) -> None:
        super().__init__(detail)


class IncorrectPassword(AppException):
    def __init__(self) -> None:
        super().__init__(messages.INCORRECT_CURRENT_PASSWORD)
