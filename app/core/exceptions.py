class AppException(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class NotFoundException(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(
            detail=f"{resource} not found",
            status_code=404,
        )