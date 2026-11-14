# Day 4: phân quyền theo workspace

## Hai tầng role

- **Role hệ thống** (`users.role`): `ADMIN` hoặc `MEMBER`. ADMIN được coi như
  OWNER của mọi workspace, không cần là member.
- **Role trong workspace** (`workspace_members.role`): `OWNER` > `EDITOR` >
  `VIEWER`. Role cao hơn có mọi quyền của role thấp hơn.

Người tạo workspace là `owner_id` và có một dòng member với role `OWNER`. Dòng
này không thể bị xóa hay hạ quyền (409), nên mỗi workspace luôn có đúng một
OWNER. Chỉ có thể mời hoặc đổi member sang `EDITOR` / `VIEWER`.

## Ma trận quyền

| Thao tác | VIEWER | EDITOR | OWNER | ADMIN |
|---|:-:|:-:|:-:|:-:|
| Tạo workspace (trở thành OWNER) | ✓ | ✓ | ✓ | ✓ |
| Xem workspace, member, project, task | ✓ | ✓ | ✓ | ✓ |
| Đổi tên / xóa workspace | | | ✓ | ✓ |
| Mời / đổi role / xóa member | | | ✓ | ✓ |
| Tạo / sửa / archive project | | ✓ | ✓ | ✓ |
| Xóa project | | | ✓ | ✓ |
| Tạo / sửa task (giao việc, đổi status, priority, due_date) | | ✓ | ✓ | ✓ |
| Xóa task do mình tạo | | ✓ | ✓ | ✓ |
| Xóa task của người khác | | | ✓ | ✓ |

`GET /workspaces` trả các workspace mà user là member; ADMIN thấy tất cả.

## Mã lỗi

- **404**: user không phải member của workspace chứa tài nguyên. Trả cùng
  message với tài nguyên không tồn tại, để người ngoài không dò được id.
- **403**: là member nhưng role không đủ, hoặc EDITOR xóa task không do mình
  tạo.
- **409**: ghi vào task của project đã archive; xóa/hạ quyền OWNER; mời người
  đã là member.
- **422**: `assignee_id` không phải member OWNER/EDITOR của workspace (VIEWER
  không sửa được task nên không được giao task).

## Quy tắc nghiệp vụ

- Task được tạo qua `POST /projects/{id}/tasks`: `project_id` lấy từ path,
  `created_by` từ token, `status` luôn là `TODO`.
- Project `ARCHIVED`: task vẫn xem được nhưng không tạo, sửa, xóa được cho tới
  khi project được mở lại (`PATCH /projects/{id}` với `status=ACTIVE`).
- Xóa member: các task trong workspace đó đang giao cho người này được bỏ
  assignee (`assignee_id = null`). Task ở workspace khác không bị ảnh hưởng.
- Xóa workspace hoặc project: DB cascade xóa project, task, label, comment bên
  trong.

## Cài đặt

- `AccessService.require_role(user, workspace_id, minimum, resource=...)`
  (`app/services/access_service.py`) là chỗ duy nhất quyết định quyền. Nó trả về
  role hiệu lực để service áp thêm quy tắc ownership (xóa task).
- Service tải tài nguyên trước (404 nếu không có), rồi gọi `require_role` với
  workspace của tài nguyên đó.
- Mỗi phương thức service chạy trong một transaction (`TransactionalService`);
  lỗi ràng buộc DB trả 409.

## Để các ngày sau

- Label (CRUD theo project, gán/bỏ label cho task) và Comment.
- Cache `GET /projects/{id}/tasks` bằng Redis, invalidate khi task thay đổi.
- Gửi email notification khi được giao task (background task).
- Chuyển quyền OWNER cho người khác chưa hỗ trợ.
