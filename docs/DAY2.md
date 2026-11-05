# Day 2 — SQLAlchemy 2.x async, relationships, repository và Alembic

Tài liệu này nối tiếp đúng code Day 1 trong workspace `taskhub`. Bạn thực hiện lần lượt các bước bên dưới; các khối code có đường dẫn là nội dung cần tạo hoặc thay thế tại đường dẫn đó. Đây là hướng dẫn thực hành, code ứng dụng hiện tại vẫn là Day 1.

## 1. Mục tiêu và lịch học 8 giờ

Hiện tại project có luồng:

```text
HTTP → tasks.py → TaskService → TaskRepository → dict trong RAM
```

Sau Day 2:

```text
HTTP → async endpoint → async service → async repository → AsyncSession → PostgreSQL
```

| Thời gian | Thực hành | Kết quả kiểm tra |
| --- | --- | --- |
| 0–1h | Dependency, PostgreSQL, settings, engine/session | Kết nối được DB |
| 1–3h | Models và relationships | Có đủ metadata của 8 bảng |
| 3–4h | Alembic async | Migration tạo đủ bảng |
| 4–6h | BaseRepository, TaskRepository, service, dependency | CRUD thực sự ghi vào DB |
| 6–7h | Phân trang, filters, dữ liệu mẫu | Danh sách trả đúng trang và điều kiện |
| 7–8h | Swagger, khởi động lại, migration check | Dữ liệu còn sau restart, DB khớp models |

Day 2 hoàn thành tầng dữ liệu cho toàn bộ domain và tích hợp CRUD Task. Auth, quyền OWNER/EDITOR/VIEWER, các API nghiệp vụ còn lại thuộc những ngày tiếp theo. `Notification` có trong mô tả domain nhưng chưa có schema cụ thể trong đề; hôm nay thực hiện 8 bảng đã được chỉ định.

## 2. Chuẩn bị môi trường

Chạy lệnh tại thư mục gốc project bằng PowerShell. `venv` hiện có dùng Python **3.12.7**; lệnh `python` ngoài venv trong máy này đang trỏ đến Python 3.8, không chạy được các kiểu như `str | None` và `StrEnum` của project.

```powershell
.\venv\Scripts\python.exe --version
.\venv\Scripts\python.exe -m pip install "SQLAlchemy[asyncio]>=2.0,<2.1" "alembic>=1.13,<2" "asyncpg>=0.29,<1"
```

`pydantic-settings` và `python-dotenv` đã có trong requirements hiện tại. Sau khi cài thành công, cập nhật dependency đã cài:

```powershell
.\venv\Scripts\python.exe -m pip freeze | Set-Content -Encoding utf8 requirements.txt
```

Chọn PostgreSQL **16**, một trong hai DB được đề bài cho phép. Cần có một PostgreSQL server đang chạy. Nếu dùng PostgreSQL cài trực tiếp, chạy SQL sau bằng tài khoản quản trị qua psql hoặc pgAdmin, từng câu lệnh với autocommit:

```sql
CREATE ROLE taskhub WITH LOGIN PASSWORD 'taskhub_dev';
CREATE DATABASE taskhub OWNER taskhub;
```

Nếu bạn đã có Docker Desktop, có thể dùng container thay cho cài PostgreSQL trực tiếp:

```powershell
docker run --name taskhub-day2-db -e POSTGRES_USER=taskhub -e POSTGRES_PASSWORD=taskhub_dev -e POSTGRES_DB=taskhub -p 5432:5432 -v taskhub_day2_pgdata:/var/lib/postgresql/data -d postgres:16
docker logs taskhub-day2-db
```

Chỉ chọn một cách. Lệnh Docker trên tạo DB và tài khoản sẵn; không chạy lại hai câu SQL nếu dùng cách này. Nếu container đã được tạo, dùng `docker start taskhub-day2-db`. Khi log báo sẵn sàng nhận kết nối mới chuyển sang bước migration. Nếu port 5432 đang được dùng, đổi port host thành `5433:5432` và đổi port trong URL tương ứng.

Tạo `.env` ở gốc project:

```dotenv
DATABASE_URL=postgresql+asyncpg://taskhub:taskhub_dev@localhost:5432/taskhub
```

Tạo `.env.example` với cùng nội dung mẫu để người khác biết cách cấu hình. `.gitignore` hiện đã bỏ qua `.env`; commit `.env.example`. Mật khẩu trên chỉ là ví dụ cho DB học tập local. Nếu mật khẩu thật chứa ký tự đặc biệt, URL-encode phần mật khẩu.

## 3. Cấu trúc cần có

```text
taskhub/
├── .env
├── .env.example
├── alembic.ini                       # sinh bởi alembic init
├── alembic/
│   ├── env.py
│   └── versions/                     # các migration được commit
├── scripts/
│   ├── __init__.py                   # file rỗng
│   └── seed_day2.py
└── app/
    ├── core/
    │   ├── __init__.py               # file rỗng
    │   ├── config.py
    │   └── enums.py
    ├── db/
    │   ├── __init__.py               # file rỗng
    │   ├── base.py
    │   └── session.py
    ├── models/
    │   ├── __init__.py
    │   └── domain.py
    ├── repositories/
    │   ├── base.py
    │   └── task_repository.py        # thay bản in-memory
    ├── schemas/task.py               # sửa
    ├── services/task_service.py      # sửa
    ├── api/deps.py                   # sửa
    ├── api/v1/endpoints/tasks.py     # sửa
    └── main.py                      # sửa lifespan
```

## 4. Settings, Base và session

Tạo các thư mục/package mới và những file `__init__.py` rỗng như cây trên.

```python
# app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# app/db/base.py
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
```

```python
# app/db/session.py
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
```

Engine quản lý connection pool; `SessionFactory` tạo session. Dependency `get_db` cung cấp session cho từng request và context manager đóng session khi kết thúc, rollback transaction còn dang dở. Service sẽ kết thúc transaction ghi trước khi trả kết quả. Không cache repository hoặc session bằng `lru_cache` như bản in-memory; chỉ cache settings. Không chia sẻ một `AsyncSession` cho nhiều tác vụ chạy đồng thời. [SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [FastAPI dependency với yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/).

`expire_on_commit=False` cho phép đọc thuộc tính đã nạp sau commit mà không tự phát sinh truy vấn. Thao tác I/O như execute, flush, refresh, delete và commit cần `await`; `session.add()` chỉ đưa object vào session nên không cần `await`.

## 5. Enums dùng chung cho ORM và schema

Chuyển `TaskStatus`, `TaskPriority` từ schema sang file dùng chung để models không phụ thuộc vào tầng API. Các giá trị vẫn giữ nguyên như Day 1.

```python
# app/core/enums.py
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class WorkspaceRole(StrEnum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"
```

## 6. Models và relationships

Đọc quan hệ trước khi gõ code:

- User sở hữu Workspace; User tham gia Workspace thông qua WorkspaceMember có role.
- Workspace có nhiều Project; Project có nhiều Task và Label.
- Task có một người tạo, có thể có một người được giao; cả hai FK đều trỏ tới User.
- Task và Label có quan hệ nhiều–nhiều qua `task_labels`.
- Task có nhiều Comment; Comment có một tác giả.

`ForeignKey` là ràng buộc trong DB. `relationship()` là cách điều hướng object ORM, không thay thế FK. Quan hệ có `role` riêng như WorkspaceMember cần một model liên kết; `task_labels` chỉ chứa hai khóa nên dùng `Table`. [SQLAlchemy relationship patterns](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html).

Để dễ theo dõi trong Day 2, đặt models cùng một file. `TimestampMixin` chỉ áp dụng cho các bảng có `created_at` trong đề.

```python
# app/models/domain.py
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer,
    String, Table, Text, UniqueConstraint, func, true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ProjectStatus, TaskPriority, TaskStatus, UserRole, WorkspaceRole,
)
from app.db.base import Base


def enum_column(enum_class, name):
    # VARCHAR + CHECK: tránh vòng đời CREATE/DROP TYPE của PostgreSQL enum
    # trong bài migration đầu tiên. Dữ liệu vẫn bị ràng buộc ở DB.
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


task_labels = Table(
    "task_labels",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"),
        default=UserRole.MEMBER, server_default=UserRole.MEMBER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    owner: Mapped[User] = relationship(lazy="raise")
    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", lazy="raise", passive_deletes="all"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace", lazy="raise", passive_deletes="all"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        enum_column(WorkspaceRole, "workspace_role"),
        default=WorkspaceRole.VIEWER, server_default=WorkspaceRole.VIEWER.value,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members", lazy="raise")
    user: Mapped[User] = relationship(lazy="raise")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus, "project_status"),
        default=ProjectStatus.ACTIVE, server_default=ProjectStatus.ACTIVE.value,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="projects", lazy="raise")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", lazy="raise", passive_deletes="all"
    )
    labels: Mapped[list["Label"]] = relationship(
        back_populates="project", lazy="raise", passive_deletes="all"
    )


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, "task_status"),
        default=TaskStatus.TODO, server_default=TaskStatus.TODO.value, index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        enum_column(TaskPriority, "task_priority"),
        default=TaskPriority.MEDIUM, server_default=TaskPriority.MEDIUM.value,
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    project: Mapped[Project] = relationship(back_populates="tasks", lazy="raise")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="raise")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="raise")
    labels: Mapped[list["Label"]] = relationship(
        secondary=task_labels, back_populates="tasks", lazy="raise", passive_deletes=True
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="task", lazy="raise", passive_deletes="all"
    )


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7), default="#808080", server_default="#808080")

    project: Mapped[Project] = relationship(back_populates="labels", lazy="raise")
    tasks: Mapped[list[Task]] = relationship(
        secondary=task_labels, back_populates="labels", lazy="raise", passive_deletes=True
    )


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)

    task: Mapped[Task] = relationship(back_populates="comments", lazy="raise")
    author: Mapped[User] = relationship(lazy="raise")
```

```python
# app/models/__init__.py
from app.models.domain import (
    Comment, Label, Project, Task, User, Workspace, WorkspaceMember, task_labels,
)

__all__ = [
    "Comment", "Label", "Project", "Task", "User", "Workspace",
    "WorkspaceMember", "task_labels",
]
```

Các quyết định cần hiểu:

- Khóa chính kép ngăn một user tham gia trùng workspace và ngăn gắn trùng label.
- `assignee_id` nullable vì task có thể chưa giao cho ai; `created_by` bắt buộc.
- `foreign_keys` phân biệt hai quan hệ Task → User, tránh `AmbiguousForeignKeysError`.
- Xóa Workspace sẽ cascade Project, Task, Label, Comment và các liên kết liên quan. `passive_deletes` giao xử lý này cho FK của DB. User đang là owner/creator/assignee/author được FK bảo vệ khỏi xóa trực tiếp; chính sách vô hiệu hóa user dùng `is_active`.
- `lazy="raise"` giúp phát hiện việc truy cập relationship chưa nạp. Khi cần đọc labels hoặc comments, nạp rõ bằng `selectinload`; tránh implicit I/O trong async. [SQLAlchemy: tránh implicit I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession).
- DB chưa tự đảm bảo label và task cùng project, hoặc assignee là thành viên workspace. Đây là quy tắc cần kiểm tra trong service khi làm nghiệp vụ tương ứng.

Checkpoint: lệnh dưới phải in đủ **8** tên bảng, chưa cần DB chạy:

```powershell
.\venv\Scripts\python.exe -c "import app.models; from app.db.base import Base; from sqlalchemy.orm import configure_mappers; configure_mappers(); print(sorted(Base.metadata.tables))"
```

## 7. Alembic async và migration đầu tiên

Khởi tạo một lần ở thư mục gốc:

```powershell
.\venv\Scripts\python.exe -m alembic init -t async alembic
```

Lệnh sinh `alembic.ini`, `alembic/env.py`, template và thư mục versions. Thay toàn bộ `alembic/env.py` bằng:

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401 -- đăng ký tất cả model vào metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        get_settings().database_url, poolclass=pool.NullPool
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
```

URL lấy từ `.env` trực tiếp nên không cần đặt mật khẩu trong `alembic.ini`. `run_sync` nối connection async với API migration đồng bộ của Alembic. [Alembic asyncio cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).

Đảm bảo PostgreSQL đang chạy rồi thực hiện:

```powershell
.\venv\Scripts\python.exe -m alembic revision --autogenerate -m "create taskhub tables"
```

**Mở và đọc file vừa sinh trong `alembic/versions/` trước khi upgrade.** `upgrade()` phải tạo đủ 8 bảng và ràng buộc; `downgrade()` xóa theo chiều ngược phụ thuộc. Không chấp nhận file chỉ có `pass`. Autogenerate tạo bản nháp cần review, không phát hiện hoàn hảo mọi thay đổi, nhất là rename và thay đổi một số constraint. [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m alembic current
.\venv\Scripts\python.exe -m alembic check
```

Kiểm tra bằng pgAdmin hoặc psql:

```sql
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

Có 8 bảng nghiệp vụ và bảng `alembic_version`. Không gọi `Base.metadata.create_all()` ở startup khi dùng migrations; Alembic quản lý lịch sử schema. Sau mỗi lần sửa model: tạo revision mới → review → upgrade. Commit cả `alembic.ini`, env/template và các revision.

## 8. Cập nhật Pydantic schemas

Thay `app/schemas/task.py`. Thêm các FK của đặc tả; danh sách chuyển từ `skip/limit` sang `page/limit` và có `total`. Hai nullable fields `description`, `due_date` và `assignee_id` cho phép xóa giá trị bằng JSON null. Với title/status/priority, được bỏ qua khi PATCH nhưng không được gửi null.

```python
# app/schemas/task.py
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_id: int | None = Field(default=None, gt=0)


class TaskCreate(TaskBase):
    project_id: int = Field(gt=0)
    created_by: int = Field(gt=0)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> "TaskUpdate":
        for name in ("title", "status", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    created_at: datetime


class TaskPage(BaseModel):
    items: list[TaskRead]
    total: int
    page: int
    limit: int
```

`created_by` do client gửi chỉ là giao diện tạm cho bài DB Day 2. Khi làm auth, xóa field này khỏi input và lấy user ID từ `get_current_user`. Khi bổ sung `POST /projects/{id}/tasks`, lấy `project_id` từ path. Hôm nay giữ prefix `/api/v1/tasks` của Day 1 để tập trung kiểm tra tầng DB.

## 9. BaseRepository[T] và TaskRepository

Repository chỉ thao tác ORM, không phụ thuộc Pydantic hoặc HTTP. Repository dùng `flush()` để gửi thay đổi vào transaction và nhận ID; service quản lý commit/rollback cho cả một nghiệp vụ. Nhờ đó sau này tạo task và notification có thể cùng thành công hoặc cùng rollback.

```python
# app/repositories/base.py
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    # Bản dùng cho entity có khóa chính đơn kiểu int.
    # Bảng liên kết khóa kép dùng repository chuyên biệt khi cần.
    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def get(self, item_id: int) -> T | None:
        return await self.session.get(self.model, item_id)

    async def list(self, *, offset: int = 0, limit: int = 20) -> list[T]:
        stmt = select(self.model).order_by(*self.model.__table__.primary_key.columns)
        result = await self.session.scalars(stmt.offset(offset).limit(limit))
        return list(result.all())

    async def create(self, values: dict[str, Any]) -> T:
        item = self.model(**values)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update(self, item: T, values: dict[str, Any]) -> T:
        for field, value in values.items():
            setattr(item, field, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: T) -> None:
        await self.session.delete(item)
        await self.session.flush()
```

```python
# app/repositories/task_repository.py
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TaskPriority, TaskStatus
from app.models import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def list_filtered(
        self,
        *,
        page: int,
        limit: int,
        project_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> tuple[list[Task], int]:
        filters = []
        for column, value in (
            (Task.project_id, project_id),
            (Task.status, status),
            (Task.priority, priority),
            (Task.assignee_id, assignee_id),
        ):
            if value is not None:
                filters.append(column == value)

        stmt = (
            select(Task)
            .where(*filters)
            .order_by(Task.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        items = list((await self.session.scalars(stmt)).all())
        count_stmt = select(func.count()).select_from(Task).where(*filters)
        total = (await self.session.scalar(count_stmt)) or 0
        return items, total
```

`page=1` tương ứng offset 0; `page=2&limit=20` tương ứng offset 20. Luôn dùng `order_by` để thứ tự phân trang xác định. Query count áp dụng cùng bộ filter nhưng không áp dụng offset/limit. Hai query dùng mức cô lập mặc định nên total/items có thể lệch nhẹ nếu có ghi đồng thời; đủ cho bài Day 2. Filter assignee ở đây chọn một user cụ thể, chưa có lựa chọn riêng cho task chưa được giao.

## 10. Service async và transaction

Thay `app/services/task_service.py`. Để giữ cấu trúc Day 1, service trả schema hoặc `None`/bool; endpoint xử lý 404. `InvalidTaskReference` báo FK không hợp lệ, endpoint chuyển sang 422. Các lỗi constraint khác sẽ được trả 409 sau khi transaction đã rollback.

```python
# app/services/task_service.py
from app.core.enums import TaskPriority, TaskStatus
from app.models import Project, User
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate


class InvalidTaskReference(ValueError):
    pass


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo

    async def list_tasks(
        self, page: int, limit: int,
        project_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
    ) -> TaskPage:
        items, total = await self.repo.list_filtered(
            page=page, limit=limit, project_id=project_id,
            status=status, priority=priority, assignee_id=assignee_id,
        )
        return TaskPage(
            items=[TaskRead.model_validate(item) for item in items],
            total=total, page=page, limit=limit,
        )

    async def get_task(self, task_id: int) -> TaskRead | None:
        task = await self.repo.get(task_id)
        return TaskRead.model_validate(task) if task is not None else None

    async def create_task(self, data: TaskCreate) -> TaskRead:
        async with self.repo.session.begin():
            if await self.repo.session.get(Project, data.project_id) is None:
                raise InvalidTaskReference("Project not found")
            if await self.repo.session.get(User, data.created_by) is None:
                raise InvalidTaskReference("Creator not found")
            if data.assignee_id is not None:
                if await self.repo.session.get(User, data.assignee_id) is None:
                    raise InvalidTaskReference("Assignee not found")
            task = await self.repo.create(data.model_dump())
            return TaskRead.model_validate(task)

    async def update_task(self, task_id: int, data: TaskUpdate) -> TaskRead | None:
        async with self.repo.session.begin():
            task = await self.repo.get(task_id)
            if task is None:
                return None
            changes = data.model_dump(exclude_unset=True)
            assignee_id = changes.get("assignee_id")
            if assignee_id is not None:
                if await self.repo.session.get(User, assignee_id) is None:
                    raise InvalidTaskReference("Assignee not found")
            task = await self.repo.update(task, changes)
            return TaskRead.model_validate(task)

    async def delete_task(self, task_id: int) -> bool:
        async with self.repo.session.begin():
            task = await self.repo.get(task_id)
            if task is None:
                return False
            await self.repo.delete(task)
            return True
```

`async with session.begin()` commit khi block thành công, rollback nếu có exception; khi hàm `return` từ bên trong block, context vẫn kết thúc transaction trước khi trả kết quả. `flush()` không đồng nghĩa commit. Không đặt commit ở phần sau `yield` của dependency.

Mẫu này giả định mỗi request gọi một phương thức service và chưa chạy query trước khi vào phương thức ghi. Query cũng có thể tự mở transaction (autobegin). Khi làm auth dependency đọc DB ở Day 3, cần tổ chức lại transaction chung ở tầng nghiệp vụ hoặc dùng commit/rollback rõ ràng; không mở `begin()` lồng lên transaction đã tồn tại.

## 11. Dependency và router

Thay `app/api/deps.py`; repository được tạo từ session request thay cho singleton chứa dict:

```python
# app/api/deps.py
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.task_repository import TaskRepository
from app.services.task_service import TaskService

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_task_service(
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
) -> TaskService:
    return TaskService(repo)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
```

Hai dependency factory chỉ tạo object nên vẫn dùng `def`; endpoint có gọi I/O phải chuyển sang `async def` và `await`.

```python
# app/api/v1/endpoints/tasks.py
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import TaskServiceDep
from app.core.enums import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskPage, TaskRead, TaskUpdate
from app.services.task_service import InvalidTaskReference

router = APIRouter()


@router.get("", response_model=TaskPage)
async def list_tasks(
    service: TaskServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    project_id: int | None = Query(None, gt=0),
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: int | None = Query(None, gt=0),
):
    return await service.list_tasks(page, limit, project_id, status, priority, assignee_id)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, service: TaskServiceDep):
    try:
        return await service.create_task(data)
    except InvalidTaskReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Task data conflicts with database constraints") from exc


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, service: TaskServiceDep):
    task = await service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: int, data: TaskUpdate, service: TaskServiceDep):
    try:
        task = await service.update_task(task_id, data)
    except InvalidTaskReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Task data conflicts with database constraints") from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, service: TaskServiceDep):
    try:
        deleted = await service.delete_task(task_id)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Task is still referenced") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

`app/api/v1/router.py` tiếp tục include tasks với prefix `/tasks` như hiện tại. Các lỗi DB được xử lý khi block transaction đã thoát, không bắt rồi tiếp tục query trong transaction lỗi. Khi học exception handling, gom việc chuyển lỗi này vào handler chung.

## 12. Lifespan đóng connection pool

Thay `app/main.py`. Startup thử `SELECT 1` để phát hiện sớm lỗi kết nối; shutdown dispose engine. Endpoint health kiểm tra tiến trình app, không phải readiness check DB.

```python
# app/main.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.router import api_router
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="TaskHub API",
    version="0.2.0",
    description="Task Management API",
    lifespan=lifespan,
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
```

## 13. Seed dữ liệu để tạo Task có FK hợp lệ

Trước khi POST task cần có User → Workspace → Project. Tạo `scripts/__init__.py` rỗng và script dưới. Script dùng transaction riêng, in ID thực tế và có thể chạy lại trên DB học tập của bạn mà không tạo trùng bộ demo tuần tự.

```python
# scripts/seed_day2.py
import asyncio

from sqlalchemy import select

from app.core.enums import WorkspaceRole
from app.db.session import SessionFactory, engine
from app.models import Project, User, Workspace, WorkspaceMember


async def main() -> None:
    try:
        async with SessionFactory() as session:
            async with session.begin():
                user = await session.scalar(
                    select(User).where(User.email == "day2@example.com")
                )
                if user is None:
                    user = User(
                        email="day2@example.com", full_name="Day 2 Demo",
                        hashed_password="DAY2_DEMO_LOGIN_DISABLED",
                        is_active=False,
                    )
                    session.add(user)
                    await session.flush()

                workspace = await session.scalar(
                    select(Workspace).where(
                        Workspace.owner_id == user.id, Workspace.name == "Day 2 Workspace"
                    ).order_by(Workspace.id)
                )
                if workspace is None:
                    workspace = Workspace(name="Day 2 Workspace", owner_id=user.id)
                    session.add(workspace)
                    await session.flush()

                member = await session.get(WorkspaceMember, (workspace.id, user.id))
                if member is None:
                    session.add(WorkspaceMember(
                        workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
                    ))

                project = await session.scalar(
                    select(Project).where(
                        Project.workspace_id == workspace.id, Project.name == "Day 2 Project"
                    ).order_by(Project.id)
                )
                if project is None:
                    project = Project(workspace_id=workspace.id, name="Day 2 Project")
                    session.add(project)
                    await session.flush()

                user_id, workspace_id, project_id = user.id, workspace.id, project.id
            print(f"created_by={user_id}, workspace_id={workspace_id}, project_id={project_id}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

Tài khoản demo không dùng đăng nhập; password trên là marker, không phải password hash thật. Khi triển khai auth, tạo user mới qua register hoặc seed lại với hash hợp lệ và `is_active=True`.

```powershell
.\venv\Scripts\python.exe -m scripts.seed_day2
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Mở Swagger: `http://127.0.0.1:8000/docs`.

## 14. Kiểm tra theo luồng

### Tạo và đọc lại

POST `/api/v1/tasks` với body dưới. **Thay `project_id`, `created_by`, `assignee_id` bằng ID script vừa in**, không mặc định rằng chúng luôn là 1:

```json
{
  "project_id": 1,
  "created_by": 1,
  "assignee_id": 1,
  "title": "Học SQLAlchemy async",
  "description": "Thay repository in-memory bằng PostgreSQL",
  "status": "TODO",
  "priority": "HIGH"
}
```

Kỳ vọng 201, có ID tự tăng và `created_at` do DB tạo. Ghi lại ID trả về; GET `/api/v1/tasks/{id}` phải đọc được task đó.

### Sửa, filter và phân trang

PATCH `/api/v1/tasks/{id}`:

```json
{"status": "IN_PROGRESS", "description": null, "assignee_id": null}
```

Kỳ vọng cập nhật status và xóa hai giá trị nullable, các field còn lại giữ nguyên. Gửi `{"title": null}` hoặc `{"status": null}` phải nhận 422 trước khi query DB.

Tạo thêm 2 task, rồi thử:

```text
GET /api/v1/tasks?page=1&limit=2
GET /api/v1/tasks?page=2&limit=2
GET /api/v1/tasks?status=IN_PROGRESS&priority=HIGH
GET /api/v1/tasks?project_id=1&assignee_id=1
```

Response mẫu (items chứa object TaskRead):

```json
{"items": [], "total": 0, "page": 1, "limit": 2}
```

Với DB chỉ có 3 task, trang 1 có 2 item, trang 2 có 1 item, cả hai trang có total 3. `limit=101`, `page=0`, status không thuộc enum phải trả 422.

### Kiểm tra persistence và lỗi

1. Dừng Uvicorn bằng Ctrl+C, chạy lại; task vẫn đọc được. Đây là khác biệt quan trọng với Day 1.
2. POST với project hoặc creator không tồn tại → 422, không thêm row dở dang.
3. GET/PATCH/DELETE ID không tồn tại → 404.
4. DELETE task tồn tại → 204, body rỗng; GET lại → 404.
5. Sau một request lỗi FK, tạo task hợp lệ lại phải thành công; session lỗi không được giữ cho request sau.
6. Chạy `alembic check` để xác nhận không có thay đổi schema chưa được migration phát hiện.

### Kiểm tra trực tiếp relationship

Khi cần đọc label của task trong một repository, dùng mẫu query sau trong hàm async có session; đây là ví dụ bổ sung, không phải file cần thay thế:

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Task


async def read_task_with_labels(session, task_id: int):
    stmt = select(Task).options(selectinload(Task.labels)).where(Task.id == task_id)
    task = await session.scalar(stmt)
    if task is not None:
        print([label.name for label in task.labels])
    return task
```

Thử tạo Label cùng project và gắn vào `task.labels` trong một transaction, commit rồi đọc lại bằng query trên. Gắn trùng cùng cặp ID phải bị PK của `task_labels` chặn. Tạo Comment với task/author hợp lệ rồi xóa task phải xóa cả comment và dòng liên kết label, nhưng giữ lại bản thân Label. Nếu quan hệ chưa nạp, dùng `selectinload` hoặc refresh tường minh trước khi sửa collection.

### Thử downgrade trên DB dùng thử

Trước khi seed dữ liệu quan trọng, bạn có thể kiểm tra vòng upgrade → downgrade → upgrade trên **DB dùng thử riêng**. Với migration đầu tiên, downgrade xóa các bảng và dữ liệu nghiệp vụ trong DB đang trỏ tới; chỉ chạy khi đã xác nhận URL là DB thử có thể xóa:

```powershell
.\venv\Scripts\python.exe -m alembic downgrade base
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m alembic check
```

Không dùng `stamp head` để chữa lỗi thiếu bảng: stamp chỉ đổi revision marker, không chạy DDL.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân và hướng xử lý |
| --- | --- |
| ImportError với `StrEnum` hoặc cú pháp type | Đang chạy Python ngoài venv; dùng `.\venv\Scripts\python.exe` |
| `ModuleNotFoundError: asyncpg` | Cài dependency vào đúng venv |
| `database_url Field required` | Thiếu `.env`, thiếu biến hoặc chạy lệnh ngoài thư mục gốc |
| Connection refused / password authentication failed | DB chưa chạy hoặc URL/port/tài khoản sai |
| Migration rỗng | Chưa import models trước khi gán `target_metadata` |
| `relation ... does not exist` | Chưa upgrade hoặc app và Alembic đang trỏ hai DB khác nhau |
| `AmbiguousForeignKeysError` | Thiếu foreign_keys cho creator/assignee |
| `MissingGreenlet` | Có I/O ngầm khi đọc relationship/thuộc tính hết hạn; nạp rõ relationship và giữ expire_on_commit=False |
| `A transaction is already begun` | Query đã autobegin rồi mới mở begin; đặt cả đọc và ghi nghiệp vụ bên trong cùng block transaction |
| PATCH làm mất field chưa gửi | Dùng `model_dump()` thay vì `model_dump(exclude_unset=True)` |
| Tạo task lỗi FK | Seed trước, dùng đúng ID; không bỏ FK để né lỗi |
| Không thấy task của Day 1 trong DB | Dữ liệu RAM của Day 1 chưa được lưu DB; tạo lại qua API |

## 16. Checklist hoàn thành Day 2

- [ ] Hiểu engine, session, transaction và flush/commit khác nhau thế nào.
- [ ] Có đủ 8 bảng, các FK và 2 bảng liên kết có khóa chính kép.
- [ ] Phân biệt FK, relationship, `back_populates` và eager loading.
- [ ] Alembic tạo được DB từ rỗng; `current` ở head; `check` không phát hiện lệch metadata.
- [ ] BaseRepository[T] có get/list/create/update/delete async và được TaskRepository sử dụng.
- [ ] Endpoint, service và repository chờ I/O bằng await.
- [ ] Session theo request, không cache session/repository; ghi thành công commit, lỗi rollback.
- [ ] Task CRUD qua PostgreSQL, tồn tại sau khi restart app.
- [ ] Filter status/priority/assignee/project và page+limit hoạt động, total theo cùng filter.
- [ ] PATCH phân biệt field bỏ qua với null; lỗi input/FK/không tồn tại trả mã phù hợp.
- [ ] Thử được quan hệ task-label và task-comment cùng hành vi cascade.
- [ ] Commit models, migration và requirements; `.env` không nằm trong commit.

Commit gợi ý sau khi đã chạy các kiểm tra:

```powershell
git status --short
git add app alembic alembic.ini scripts requirements.txt .env.example docs/DAY2.md
git diff --cached --stat
git commit -m "feat: day 2 async database and migrations"
```

Đến đây bạn có nền dữ liệu để làm auth và RBAC ở các ngày tiếp theo. Điểm cần thay đầu tiên khi thêm auth là nguồn `created_by` và ranh giới transaction nếu auth dependency đã đọc DB.
