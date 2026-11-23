# Cấp quyền quản trị

Trang `/admin` chỉ hiện các mục quản trị cho tài khoản có vai trò `admin`. Từ 23/11/2026 trang này không còn ghi cách cấu
hình cho tài khoản thường (trước đó câu báo lỗi nêu tên biến môi trường và nơi đặt nó trên Render).

- Vai trò `admin` được cấp **lúc đăng nhập** cho email nằm trong biến môi trường `TERRATWIN_ADMIN_EMAILS` của dịch vụ API
  (Render → `terratwin-api` → Environment). Nhiều email cách nhau bằng dấu phẩy.
- Vừa thêm email vào biến: đăng xuất rồi đăng nhập lại.
- Email phải đúng chính tả, không thừa dấu cách.
- Vai trò chỉ được NÂNG theo biến này, không tự hạ; bỏ quyền của email quản trị gốc phải sửa biến trên máy chủ
  (xem `THREAT_MODEL.md`, `backend/tests/test_roles.py`).
