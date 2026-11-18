from app.schemas.base import BaseSchema


class ErrorResponse(BaseSchema):
    detail: str
