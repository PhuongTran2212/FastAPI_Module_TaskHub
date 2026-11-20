# Day 8 — Review, refactor và tối ưu

Phạm vi ngày 8 tập trung vào kiểm tra chất lượng, loại trùng lặp, giảm truy vấn
dư và hoàn thiện hướng dẫn chạy. Các thay đổi được tách trên nhánh riêng từ
Day 7; PR Day 7 cần được review/merge trước.

## Kiểu dữ liệu và CI

- Chốt mypy 2.4.1 và celery-types 0.26.0 trong dependency phát triển.
- Bật strict cho toàn bộ `app`/`scripts`, plugin Pydantic, cảnh báo unreachable
  và cấu hình init typed. Không bỏ qua lỗi toàn module ứng dụng.
- Dùng kiểu native SQLAlchemy 2, scalar result có kiểu và `.one_or_none()` cho
  truy vấn theo PK/email unique; giữ nguyên `FOR UPDATE` trong refresh rotation.
- Dùng một alias `Responses` cho metadata OpenAPI để các dict ghép có kiểu
  thống nhất. Payload bên trong dùng Any vì cấu trúc mở của FastAPI/OpenAPI.
- Khoanh đúng biên dynamic: cast `app.state.task_cache` theo kiểu do lifespan
  quản lý; JSON của smoke script kiểm tra object trước khi sử dụng.
- SMTP_SSL và SMTP được khởi tạo tường minh, vẫn xác minh certificate/hostname;
  task Celery có kiểu tham số/giá trị trả về. Không thêm dependency dev vào image.
- CI bắt buộc Ruff lint, Ruff format, mypy và pytest trước khi merge.

## DRY và hiệu năng

- `BaseRepository._ordered_select()` dùng chung thứ tự theo toàn bộ PK cho
  list/list_page, gồm cả khóa ghép workspace_members.
- Dùng chung `TaskDueDate` cho request Create/PATCH. Read model vẫn đọc được
  task đã quá hạn; bỏ trống due_date trong PATCH không thay đổi dữ liệu và null
  vẫn có thể xóa ngày hạn.
- Bỏ refresh toàn bản ghi sau flush trong repository. PostgreSQL INSERT
  RETURNING đã trả ID/server defaults; các model hiện tại không có field
  server-generated khi UPDATE cần tải lại.
- Regression test ghi một task rồi update: **1 INSERT, 3 UPDATE, 0 SELECT**.
  Hai UPDATE bổ sung là tăng project cache version, vẫn nằm cùng transaction.
  Test kiểm tra created_at/status/priority rồi đọc lại ở session khác để so
  khớp dữ liệu đã lưu. Trước refactor, mỗi create/update gọi thêm một refresh.
- Rà soát quan hệ: task→project, comment→task→project, label→project và
  member→user dùng eager loading; các relationship còn lại dùng lazy="raise"
  để tránh truy vấn ngầm. Index FK/filter, label reverse index và token expiry
  đã được quản lý bằng migration ở các ngày trước.
- Đây là kiểm tra số round trip SQL, chưa phải benchmark throughput/latency.
  Offset pagination và DB lookup quyền truy cập vẫn là chi phí được giữ theo
  thiết kế; không hứa hẹn số RPS hay phần trăm tăng tốc khi chưa đo tải thực tế.

## Kiểm tra hồi quy và khả năng chạy

- Toàn bộ test API/DB, RBAC/ownership, validation, cache, refresh-token
  concurrency, labels/comments, SMTP/TLS và cleanup chạy qua PostgreSQL thật.
- Bổ sung test ngân sách truy vấn/defaults, thứ tự khóa ghép, task đã quá hạn,
  due_date PATCH và dọn user smoke khi login thất bại.
- Smoke script đưa login vào khối cleanup để user tạm vẫn được xóa nếu login
  thất bại ngay sau register.
- CI Docker giữ luồng API→broker→worker→Mailpit và Beat cleanup trên stack
  PostgreSQL 16/Redis 7. README mô tả setup, env vars, Swagger/ReDoc, test và
  xử lý lỗi Windows từng gặp khi cài Docker.

Chạy kiểm tra từ thư mục gốc:

```powershell
.\venv\Scripts\python.exe -m ruff check app tests scripts
.\venv\Scripts\python.exe -m ruff format --check app tests scripts
.\venv\Scripts\python.exe -m mypy
.\venv\Scripts\python.exe -m pytest -q
```

Tài liệu tham khảo: [SQLAlchemy server-generated defaults](https://docs.sqlalchemy.org/en/20/orm/persistence_techniques.html#case-1-non-primary-key-returning-or-equivalent-is-supported),
[mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html).
