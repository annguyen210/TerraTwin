# Pháp nhân để thu tiền TerraTwin — hồ sơ soạn sẵn

> Soạn 18/10/2026. Đây là **bản chuẩn bị**, không phải tư vấn pháp lý. Thủ tục đăng ký kinh doanh và thuế thay đổi nhiều
> trong 2025–2026 (sắp xếp chính quyền hai cấp từ 1/7/2025, bỏ thuế khoán hộ kinh doanh từ 1/1/2026) — kiểm lại trên cổng
> chính thức ngay lúc nộp. Phần mã thu tiền đã xong (VietQR + SePay, xem `DEPLOY.md`); phần dưới đây là phần **chỉ chủ dự án
> làm được**, vì phải đăng nhập VNeID, khai số định danh cá nhân và ký bằng chính danh.

## 1. Chọn loại nào

| | Hộ kinh doanh | Công ty TNHH một thành viên |
|---|---|---|
| Hợp với | Thu tiền lẻ từ người dùng (gói Mở rộng 299.000 đ/tháng), thử thị trường | Hợp đồng với ngân hàng, bảo hiểm, doanh nghiệp (gói Doanh nghiệp), gọi vốn, dự thi cần tư cách pháp nhân |
| Tư cách pháp nhân | **Không** (chủ hộ chịu trách nhiệm bằng toàn bộ tài sản) | **Có** (chịu trách nhiệm trong vốn điều lệ) |
| Nơi nộp | Cơ quan đăng ký kinh doanh cấp xã nơi đặt địa điểm kinh doanh | Phòng Đăng ký kinh doanh cấp tỉnh |
| Nộp online | Cổng Dịch vụ công quốc gia `dichvucong.gov.vn`, đăng nhập VNeID mức 2 | `dangkykinhdoanh.gov.vn`, đăng nhập VNeID mức 2 / chữ ký số |
| Hoá đơn | Hoá đơn điện tử theo quy định cho hộ kê khai | Hoá đơn điện tử bắt buộc |

**Đề xuất:** bắt đầu bằng **hộ kinh doanh** để thu tiền gói Mở rộng ngay; chuyển thành công ty khi có khách doanh nghiệp đầu
tiên hoặc khi cuộc thi yêu cầu pháp nhân.

## 2. Thông tin cần điền (chủ dự án tự điền — KHÔNG đưa vào repo)

- Tên hộ / tên công ty: gợi ý `HỘ KINH DOANH TERRATWIN` hoặc `CÔNG TY TNHH TERRATWIN` (tra trùng tên trên
  `dangkykinhdoanh.gov.vn` trước).
- Địa chỉ trụ sở / địa điểm kinh doanh (có thể là nhà ở của chủ hộ nếu chính quyền địa phương chấp nhận).
- Họ tên, số định danh cá nhân, ngày sinh, nơi thường trú của chủ hộ / chủ sở hữu.
- Vốn kinh doanh / vốn điều lệ (phần mềm chạy 0 đồng trên gói miễn phí — vốn ghi theo khả năng thật).
- Ngành nghề — chọn mã trên cổng theo Hệ thống ngành kinh tế hiện hành; tìm theo tên:
  - **Lập trình máy vi tính** (ngành chính)
  - **Xử lý dữ liệu, cho thuê và các hoạt động liên quan** (hồ sơ đất, API)
  - **Cổng thông tin**
  - **Hoạt động tư vấn kỹ thuật có liên quan khác** (thẩm định thửa cho ngân hàng / bảo hiểm)
- Email, số điện thoại liên hệ; tài khoản ngân hàng (dùng đúng tài khoản sẽ đặt cho VietQR + SePay).

## 3. Các bước

1. Tra trùng tên doanh nghiệp/hộ trên `dangkykinhdoanh.gov.vn`.
2. Tra nhãn hiệu "TerraTwin" trên `wipopublish.ipvietnam.gov.vn` (mục Nhãn hiệu, tìm theo tên) — nếu chưa ai đăng ký thì
   nộp đơn nhãn hiệu (nhóm 9 phần mềm, nhóm 42 dịch vụ phần mềm/SaaS) tại Cục Sở hữu trí tuệ, online được.
3. Nộp hồ sơ đăng ký hộ kinh doanh / doanh nghiệp online (mục 1), ký xác thực bằng VNeID; theo dõi kết quả qua email.
4. Nhận giấy chứng nhận → đăng ký thuế (mã số thuế hộ/doanh nghiệp đi kèm), đăng ký hoá đơn điện tử với cơ quan thuế.
5. Mở / gắn tài khoản ngân hàng đứng tên hộ hoặc công ty → đặt `TERRATWIN_VIETQR_*` và nối SePay (`DEPLOY.md`).
6. Dữ liệu cá nhân (Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15): TerraTwin xử lý email, toạ độ thửa, ảnh thực địa → lập hồ sơ
   đánh giá tác động xử lý dữ liệu cá nhân theo hướng dẫn của cơ quan chuyên trách (Bộ Công an); `/privacy` hiện ghi "bản
   nháp, chờ luật sư duyệt" — đổi thành bản chính thức khi xong.
7. Cập nhật `/pricing` và `/terms`: tên pháp nhân, mã số thuế, địa chỉ, đầu mối liên hệ.

## 4. Phần mã đã sẵn sàng (không cần làm thêm)

- VietQR chuẩn NAPAS/EMVCo dựng trên máy chủ — `backend/app/services/vietqr.py`.
- SePay webhook tự kích hoạt gói khi tiền vào đúng mã, đủ giá; chống cấp hai lần — `backend/app/services/sepay.py`,
  `POST /api/payments/sepay`; quản trị xem giao dịch ở /admin → Nâng hạn mức.
- Không lưu số thẻ, không lưu số tài khoản người chuyển.
