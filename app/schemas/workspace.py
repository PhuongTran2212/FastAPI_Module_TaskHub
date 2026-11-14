from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field

from app.core.constants import MIN_TEXT_LENGTH, WORKSPACE_NAME_MAX_LENGTH
from app.core.enums import WorkspaceRole
from app.models import User, WorkspaceMember
from app.schemas.base import BaseSchema, reject_null
from app.schemas.pagination import Page
from app.schemas.user import Email

WorkspaceName = Annotated[
    str,
    Field(min_length=MIN_TEXT_LENGTH, max_length=WORKSPACE_NAME_MAX_LENGTH),
]

# OWNER chỉ có một (người tạo workspace), nên chỉ mời/đổi sang EDITOR hoặc VIEWER
MemberRole = Literal[WorkspaceRole.EDITOR, WorkspaceRole.VIEWER]


class WorkspaceCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName


class WorkspaceUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[WorkspaceName | None, AfterValidator(reject_null)] = None


class WorkspaceRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    created_at: datetime


class WorkspacePage(Page[WorkspaceRead]):
    pass


class MemberCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    email: Email
    role: MemberRole = WorkspaceRole.VIEWER


class MemberUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    role: MemberRole


class MemberRead(BaseSchema):
    user_id: int
    email: str
    full_name: str
    role: WorkspaceRole

    @classmethod
    def from_member(cls, member: WorkspaceMember, user: User) -> "MemberRead":
        return cls(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
        )
