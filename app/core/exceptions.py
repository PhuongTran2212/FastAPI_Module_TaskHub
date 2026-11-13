from app.core import messages
from app.core.constants import BEARER_HEADERS


class AppException(Exception):
    def __init__(
        self,
        detail: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.headers = headers


class NotFoundException(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(messages.RESOURCE_NOT_FOUND.format(resource=resource), 404)


class InvalidReferenceException(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(messages.RESOURCE_NOT_FOUND.format(resource=resource), 422)


class ConflictException(AppException):
    def __init__(self, detail: str = messages.TASK_CONFLICT) -> None:
        super().__init__(detail, 409)


class UnauthorizedException(AppException):
    def __init__(self, detail: str = messages.AUTHENTICATION_REQUIRED) -> None:
        super().__init__(detail, 401, BEARER_HEADERS.copy())


class ForbiddenException(AppException):
    def __init__(self, detail: str = messages.PERMISSION_DENIED) -> None:
        super().__init__(detail, 403)


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
        super().__init__(messages.INCORRECT_CURRENT_PASSWORD, 400)
