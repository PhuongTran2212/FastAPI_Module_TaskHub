# TaskHub — FastAPI Task Management API

Sample app quản lý công việc theo workspace/project, phát triển trong 8 ngày
thực tập FastAPI. Dùng Python 3.12, SQLAlchemy 2 async, PostgreSQL 16,
Alembic, Redis 7 và Celery. Phiên bản dependency được chốt trong
`requirements.txt` và `requirements-dev.txt`.

## Chức năng

- Đăng ký, đăng nhập JWT, refresh token rotation/reuse detection và logout.
- Xem/sửa hồ sơ, đổi mật khẩu; ADMIN có thể xem danh sách user.
- CRUD workspace/project/task, mời/xóa thành viên và phân quyền
  ADMIN / OWNER / EDITOR / VIEWER theo tài nguyên.
- Archive project; lọc task theo status, priority, assignee; phân trang
  `page`/`limit` và trả tổng số bản ghi.
- CRUD label trong project, gán/bỏ label cho task; thêm/xóa comment và kiểm tra
  quyền sở hữu khi xóa. Tên label phân biệt hoa thường (`Bug` và `bug` khác nhau).
- Cache danh sách task bằng Redis; phiên bản cache được tăng cùng transaction
  khi dữ liệu thay đổi, quyền truy cập luôn được kiểm tra trước khi đọc cache.
- Gửi email khi gán task bằng Celery; Beat dọn refresh token hết hạn.
- Swagger/ReDoc, error responses, Docker Compose và kiểm tra chất lượng trên CI.

## Kiến trúc

```text
app/api          Router, dependency injection, phân trang, error responses
app/schemas      Pydantic: chuẩn hóa và kiểm tra request/response
app/services     Business logic, transaction, AccessService/RBAC
app/repositories SQLAlchemy CRUD, truy vấn, khóa dòng và phân trang
app/models       ORM models, quan hệ và constraint
app/core         Settings, JWT/password, exception, Redis cache, Celery
app/jobs.py      Email worker và job dọn refresh token
alembic          Lịch sử migration
tests            API/integration, concurrency, SMTP và regression tests
scripts          Seed/demo, tạo ADMIN, smoke test Docker
```

Service quản lý transaction; repository thực hiện truy vấn. `AccessService`
gom quy tắc 404/403/409. Lifespan kiểm tra kết nối DB và quản lý Redis client.
Email chỉ được đưa vào hàng đợi sau khi transaction lưu task thành công.

## Chạy bằng Docker Compose

### Chuẩn bị

- Git, Python 3.12 (cho công cụ kiểm tra/script) và Docker Desktop chạy Linux
  containers; trên Windows chọn backend WSL 2.
- Mở Docker Desktop, kiểm tra `docker info` đã có phần Server trước khi chạy.
- Các cổng `8000` và `8025` cần trống. Dừng Uvicorn cũ bằng Ctrl+C nếu cần.

Từ PowerShell ở thư mục repo, tạo `.env` nếu chưa có:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -3.12 -c "import secrets; print(secrets.token_hex(32))"
```

Dán khóa vừa tạo vào `JWT_SECRET_KEY` trong `.env`. Mỗi môi trường dùng một khóa
riêng, tối thiểu 32 ký tự. Giá trị `CHANGE_ME` không hợp lệ. `.env` được Git và
Docker build context bỏ qua; `.env.example` chỉ là mẫu cấu hình.

```powershell
docker compose up --build --wait
docker compose ps
```

Compose chạy một migration trước, sau đó khởi động API, worker và Beat khi DB/
Redis sẵn sàng. Dữ liệu được lưu trong named volumes; đây là database riêng của
Compose, tách khỏi PostgreSQL đang cài trực tiếp trên Windows.

| Dịch vụ | Địa chỉ / cách dùng |
| --- | --- |
| Swagger | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| Health | http://127.0.0.1:8000/health |
| Mailpit | http://127.0.0.1:8025 — giữ email thử trong máy |
| PostgreSQL | Hostname `db`, cổng 5432 trong mạng Compose |
| Redis cache | `redis:6379`, DB 0 |
| Redis broker | `redis:6379`, DB 1 |

Compose bind API/Mailpit vào loopback. PostgreSQL/Redis không mở cổng ra host.
Mẫu này dành cho phát triển cục bộ; `POSTGRES_PASSWORD=taskhub_dev` là mật khẩu
demo. Nếu đổi mật khẩu sau khi đã tạo volume, cần đổi cả mật khẩu bên trong
PostgreSQL; thay `.env` không tự cập nhật user của database đã có.

```powershell
docker compose logs --tail 100 api worker beat
docker compose stop
# Chạy lại, giữ dữ liệu:
docker compose up --wait
```

### Luồng thử qua Swagger

1. POST `/api/v1/auth/register`: nhập email, full_name, password; lưu `id` user.
2. POST `/api/v1/auth/login`: lấy `access_token`.
3. Bấm Authorize, dán **chỉ chuỗi access token**, rồi Authorize → Close.
4. GET `/api/v1/users/me` phải trả 200. Nếu 401, đăng nhập lại và thay token
   trong Authorize; access token mặc định hết hạn sau 15 phút.
5. POST `/api/v1/workspaces`, lấy id workspace; POST
   `/api/v1/workspaces/{workspace_id}/projects`, lấy id project.
6. POST `/api/v1/projects/{project_id}/tasks` với title và `assignee_id` là id
   của bạn hoặc thành viên OWNER/EDITOR. Task mới có status TODO.
7. Mở Mailpit để xem email. PATCH cùng assignee hoặc `assignee_id: null` không
   gửi thêm; gán từ null sang một thành viên hợp lệ sẽ gửi email mới.

Để tạo tài khoản ADMIN trong **database Compose**, đăng ký user trước rồi chạy
script quản trị từ repo qua stdin (thay email bằng user cần quản trị):

```powershell
Get-Content scripts/make_admin.py | docker compose exec -T api python - admin@example.com
```

Quy tắc quyền, archive và ownership chi tiết: [RBAC](docs/RBAC.md).

## Chạy API trực tiếp trên máy

Cần PostgreSQL 16 và user/database ứng dụng đã được tạo. Copy `.env.example`
sang `.env` nếu chưa có, điền đúng `DATABASE_URL` và khóa JWT riêng.

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Khi chạy ngoài Docker, dùng `TASK_CACHE_ENABLED=false` nếu chưa có Redis; hoặc
cấu hình `REDIS_URL` tới Redis đang chạy. Email mặc định tắt. Để bật, cấu hình
SMTP/broker và chạy worker + một tiến trình Beat trên Linux/WSL/Docker, xem
[background jobs](docs/AUTH_NOTES.md#day-7-background-jobs). Celery không hỗ trợ
worker native Windows.

## Biến môi trường

Biến môi trường của process được ưu tiên hơn `.env`. Compose ghi đè các
hostname DB/Redis/SMTP để các container kết nối với nhau và bật email qua
Mailpit. Các tùy chọn bên dưới áp dụng theo `Settings`; xem `compose.yaml` để
biết giá trị được truyền cụ thể vào stack phát triển.

| Biến | Mặc định / ý nghĩa |
| --- | --- |
| `DATABASE_URL` | Bắt buộc, `postgresql+asyncpg://user:password@host:5432/database` |
| `JWT_SECRET_KEY` | Bắt buộc, khóa riêng dài ít nhất 32 ký tự |
| `JWT_ALGORITHM` | Chỉ HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `TASK_CACHE_ENABLED` | true |
| `TASK_CACHE_TTL_SECONDS` | 60 |
| `REDIS_TIMEOUT_SECONDS` | 0.2 |
| `REDIS_MAX_CONNECTIONS` | 10 |
| `REDIS_POOL_WAIT_SECONDS` | 0.1 |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` |
| `JOB_CONNECTION_TIMEOUT_SECONDS` | 2 |
| `JOB_MAX_RETRIES` | 3 |
| `ASSIGNMENT_EMAIL_ENABLED` | false; Compose bật true |
| `ASSIGNMENT_EMAIL_EXPIRES_SECONDS` | 3600 |
| `SMTP_HOST` / `SMTP_PORT` | localhost / 1025; Compose dùng mailpit / 1025 |
| `SMTP_FROM_EMAIL` | `taskhub@example.com` |
| `SMTP_SECURITY` | none, starttls hoặc ssl |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Cấu hình cùng nhau; đăng nhập SMTP yêu cầu TLS |
| `SMTP_TIMEOUT_SECONDS` | 5 |
| `REFRESH_CLEANUP_INTERVAL_SECONDS` | 300 (5 phút) |
| `REFRESH_CLEANUP_BATCH_SIZE` | 500 |
| `REFRESH_CLEANUP_BUDGET_SECONDS` | 30, ngân sách xử lý nhiều batch |
| `POSTGRES_PASSWORD` | Biến dành cho Compose; mặc định demo `taskhub_dev` |
| `TEST_DATABASE_URL` | Database riêng dành cho pytest, tên kết thúc bằng `_test` |
| `TEST_REDIS_URL` | Tùy chọn; pytest dùng Redis thật nếu có, fakeredis nếu bỏ trống |

Nếu mật khẩu trong URL có ký tự đặc biệt, cần URL-encode phần mật khẩu.

## Kiểm tra chất lượng và test

Cài `requirements-dev.txt`. Tạo database test riêng bằng tài khoản PostgreSQL
có quyền tạo database (nếu database này chưa tồn tại):

```sql
CREATE DATABASE taskhub_day3_test OWNER taskhub;
```

Copy `.env.test.example` sang `.env.test`, điền đúng mật khẩu. Test URL phải dùng
`postgresql+asyncpg`, tên DB kết thúc bằng `_test` và khác database ứng dụng.
Suite có chạy Alembic downgrade/upgrade và dùng các transaction thực trong test
concurrency, nên cần giữ database này riêng cho kiểm thử.

```powershell
.\venv\Scripts\python.exe -m ruff check app tests scripts
.\venv\Scripts\python.exe -m ruff format --check app tests scripts
.\venv\Scripts\python.exe -m mypy
.\venv\Scripts\python.exe -m pytest -q
```

Mypy chạy **strict trên toàn bộ `app` và `scripts`**, dùng plugin Pydantic và
stub Celery. SQLAlchemy 2 dùng kiểu native `Mapped`/`mapped_column`, không cần
plugin SQLAlchemy cũ. Test fixtures được kiểm tra bằng Ruff và pytest; không có
cấu hình bỏ qua lỗi kiểu trên toàn bộ module ứng dụng.

CI chạy cùng các lệnh trên với PostgreSQL 16 + Redis 7 thật. Job thứ hai build
image, chạy cả Compose stack và kiểm tra API → Redis → Celery → Mailpit + Beat.
Xem thêm [test setup](tests/README.md) và [review Day 8](docs/DAY8_REVIEW.md).

### Smoke test email và Beat trên Compose

Sau khi đã có Python venv/dependency, từ một stack phát triển cục bộ, chạy:

```powershell
$env:REFRESH_CLEANUP_INTERVAL_SECONDS = "5"
docker compose up --build --wait
.\venv\Scripts\python.exe scripts/smoke_background.py
# Trả lịch dọn về mặc định sau bài test:
$env:REFRESH_CLEANUP_INTERVAL_SECONDS = "300"
docker compose up --wait
```

Kết quả mong đợi:

```text
Compose smoke passed: assignment email, no-op update, beat cleanup.
```

Script tạo user/workspace riêng, gửi email vào Mailpit, kiểm tra không gửi thêm
khi giữ nguyên assignee và đợi Beat xóa token hết hạn, giữ token đã revoke nhưng
chưa hết hạn. Dữ liệu thử được dọn khi script kết thúc; email thử vẫn xem được
trong Mailpit. Đường dẫn/timeout của script dành cho stack cục bộ này.

## Lưu ý thiết kế và xử lý lỗi

- Refresh rotation nghiêm ngặt: token cũ chỉ dùng một lần; reuse thu hồi mọi
  refresh token của user. Client cần tránh refresh đồng thời. Logout không thu
  hồi access token đang còn hạn. [Chi tiết auth](docs/AUTH_NOTES.md).
- Email là best-effort: sự cố giữa commit và enqueue có thể mất thông báo;
  retry SMTP có thể gửi trùng. Chưa có transactional outbox/exactly-once.
- Redis cache lỗi thì API đọc PostgreSQL. Cache dùng TTL và version trong DB,
  không dùng quét/xóa toàn bộ Redis. [Chi tiết cache](docs/CACHING.md).
- Label list cố ý không phân trang; task/comment/user list dùng Page với total.
- `docker` chưa nhận lệnh: mở lại VS Code sau cài đặt; kiểm tra Docker Desktop
  đã cài hoàn tất. Với bản per-user, CLI thường nằm ở
  `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`.
- Docker Engine chưa kết nối: mở Docker Desktop; sau khi bật
  VirtualMachinePlatform/WSL cần Restart Windows. [Cài Docker trên Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
- Cổng 8000 bị chiếm: dừng Uvicorn cũ trước khi mở API Compose.
- Xem lỗi khởi động bằng `docker compose logs --tail 100 migrate api worker beat`.
  Dừng bằng `docker compose stop` để giữ dữ liệu trong volumes.
