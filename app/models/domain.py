from datetime import date, datetime
from app.core.constants import (
    EMAIL_MAX_LENGTH,
    LABEL_COLOR_MAX_LENGTH,
    LABEL_NAME_MAX_LENGTH,
    PASSWORD_HASH_MAX_LENGTH,
    PROJECT_NAME_MAX_LENGTH,
    TASK_TITLE_MAX_LENGTH,
    USER_FULL_NAME_MAX_LENGTH,
    WORKSPACE_NAME_MAX_LENGTH,
)
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    WorkspaceRole,
)
from app.db.base import Base

task_labels = Table(
    "task_labels",
    Base.metadata,
    Column(
        "task_id",
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        ForeignKey("labels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    email: Mapped[str] = mapped_column(
        String(EMAIL_MAX_LENGTH),
        unique=True,
    )
    full_name: Mapped[str] = mapped_column(String(USER_FULL_NAME_MAX_LENGTH))
    hashed_password: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH))

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=UserRole.MEMBER,
        server_default=UserRole.MEMBER.value,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )

class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(WORKSPACE_NAME_MAX_LENGTH))
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )

    owner: Mapped[User] = relationship(lazy="raise")

    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace",
        lazy="raise",
        passive_deletes="all",
    )

    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace",
        lazy="raise",
        passive_deletes="all",
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(
            WorkspaceRole,
            name="workspace_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=WorkspaceRole.VIEWER,
        server_default=WorkspaceRole.VIEWER.value,
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="members",
        lazy="raise",
    )
    user: Mapped[User] = relationship(lazy="raise")

class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(String(PROJECT_NAME_MAX_LENGTH))
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ProjectStatus] = mapped_column(
        Enum(
            ProjectStatus,
            name="project_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=ProjectStatus.ACTIVE,
        server_default=ProjectStatus.ACTIVE.value,
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="projects",
        lazy="raise",
    )

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project",
        lazy="raise",
        passive_deletes="all",
    )

    labels: Mapped[list["Label"]] = relationship(
        back_populates="project",
        lazy="raise",
        passive_deletes="all",
    )

class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )

    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(TASK_TITLE_MAX_LENGTH),
    )
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        index=True,
    )

    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )

    due_date: Mapped[date | None] = mapped_column(Date)

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )

    project: Mapped[Project] = relationship(
        back_populates="tasks",
        lazy="raise",
    )

    assignee: Mapped[User | None] = relationship(
        foreign_keys=[assignee_id],
        lazy="raise",
    )

    creator: Mapped[User] = relationship(
        foreign_keys=[created_by],
        lazy="raise",
    )

    labels: Mapped[list["Label"]] = relationship(
        secondary=task_labels,
        back_populates="tasks",
        lazy="raise",
        passive_deletes=True,
    )

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="task",
        lazy="raise",
        passive_deletes="all",
    )

class Label(Base):
    __tablename__ = "labels"

    __table_args__ = (
        UniqueConstraint("project_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(String(LABEL_NAME_MAX_LENGTH))

    color: Mapped[str] = mapped_column(
        String(LABEL_COLOR_MAX_LENGTH),
        default="#808080",
        server_default="#808080",
    )

    project: Mapped[Project] = relationship(
        back_populates="labels",
        lazy="raise",
    )

    tasks: Mapped[list[Task]] = relationship(
        secondary=task_labels,
        back_populates="labels",
        lazy="raise",
        passive_deletes=True,
    )

class Comment(TimestampMixin, Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )

    content: Mapped[str] = mapped_column(Text)

    task: Mapped[Task] = relationship(
        back_populates="comments",
        lazy="raise",
    )

    author: Mapped[User] = relationship(lazy="raise")