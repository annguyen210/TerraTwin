# Mô hình mối đe doạ — TerraTwin

Bản 9/10/2026 (GĐ7 kế hoạch tổng). Viết theo STRIDE trên hệ thống **đang chạy thật**, không phải hệ thống lý tưởng.
Mỗi mối đe doạ ghi biện pháp đã có (kèm tệp mã hoặc test) và rủi ro còn lại — rủi ro còn lại nói thẳng, không giấu.

## 1. Tài sản cần bảo vệ

| Tài sản | Vì sao quan trọng |
|---|---|
| **Hồ sơ đất số / hồ sơ EUDR đã ký** | Ngân hàng, người mua, nhà nhập khẩu ra quyết định tiền bạc dựa trên nó. Sửa được là mất hết giá trị. |
| **Khoá ký Ed25519** (`TERRATWIN_SIGNING_KEY`) | Ai có khoá ký được hồ sơ "thật". |
| **Sổ đăng ký + sổ minh bạch Merkle** | Chứng minh không hồ sơ nào bị sửa/xoá/lùi ngày. |
| **Tài khoản quản trị** | Xem góp ý thí điểm, nhãn kiểm định, số liệu vận hành. |
| **Dữ liệu cá nhân** (email, toạ độ thửa, ảnh thực địa, quan sát) | Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15. |
| **Số đo cảm biến IoT** | Đi vào nhật ký thửa và vòng kiểm chứng. |
| **Sổ điểm tự chấm, kết quả kiểm định mô hình** | Uy tín "công bố cả tỉ lệ sai của mình". |
| **Hạn mức nguồn dữ liệu mở** (Open-Meteo, Planetary Computer) | Bị đốt hết là mọi người dùng mất dữ liệu. |

## 2. Tác nhân

Người dùng ẩn danh · người dùng đã đăng nhập · môi giới có động cơ làm đất "sạch" · người cầm một hồ sơ giả ·
kẻ chiếm được một tài khoản · kẻ chiếm được máy chủ hoặc CSDL · **chính chủ hệ thống** (muốn lùi ngày một hồ sơ) ·
bot dò mật khẩu / dò mã · thiết bị IoT giả.

## 3. Ranh giới tin cậy

Trình duyệt ↔ web (Render, Next.js) ↔ API (Render, FastAPI) ↔ CSDL (Neon Postgres) ↔ nguồn ngoài (Open-Meteo,
Planetary Computer, OSM, Source Cooperative) · API ↔ thiết bị IoT · kho GitHub công khai (nhân chứng sổ, neo
OpenTimestamps) · chuỗi khối Bitcoin (qua máy chủ lịch OpenTimestamps).

## 4. STRIDE

| Loại | Mối đe doạ | Biện pháp đã có | Rủi ro còn lại |
|---|---|---|---|
| **S**giả danh | Dò mật khẩu | bcrypt (tiền băm SHA-256), cùng thông báo + băm giả cho email không tồn tại (chống dò tài khoản qua thời gian), giới hạn tần suất theo IP | Mật khẩu yếu do người dùng chọn |
| S | Mật khẩu quản trị bị lộ | **TOTP hai lớp** (`services/totp.py`, RFC 6238, bí mật mã hoá AES-GCM, chống dùng lại mã, 8 mã khôi phục băm SHA-256, 5 lần sai/15 phút → 429); `TERRATWIN_ADMIN_REQUIRE_2FA=1` bắt buộc với quản trị và chặn khoá API vào mục quản trị — `tests/test_gd7_2fa.py` | Cờ phải được bật sau khi chủ dự án đã thiết lập 2FA |
| S | Thiết bị IoT giả gửi số đo | Mỗi thiết bị một khoá Ed25519, ký từng số đo, seq tăng nghiêm ngặt (chống phát lại), ngưỡng vật lý — `tests/test_iot.py` | Thiết bị thật bị lấy cắp khoá |
| S | Trang giả mạo trang kiểm chứng | QR trỏ đúng tên miền; script kiểm độc lập `ops/verify_dossier.py` không cần tin trang web | Người dùng không xem tên miền |
| **T**ampering | Sửa nội dung một hồ sơ trong CSDL | SHA-256 nội dung + chữ ký Ed25519 + móc xích `prev_hash`; trang kiểm chứng chạy lại 4 phép kiểm mỗi lần mở — `tests/test_dossier.py` | — |
| T | Sửa bản in / tệp JSON trước khi đưa ngân hàng | Kiểm tệp với sổ (`/api/dossier/verify`) và offline (`ops/verify_dossier.py --file`) — `tests/test_gd4_evidence.py` (sửa 1 ký tự → đỏ) | — |
| T | Kẻ chiếm máy chủ dựng lại cả chuỗi và ký lại | Sổ minh bạch Merkle (RFC 6962), nhân chứng GitHub hằng ngày kiểm bằng chứng nhất quán (`ops/translog_witness.py`) | Khoảng hở tới lượt nhân chứng kế tiếp (≤ 12 giờ) |
| T | **Chủ hệ thống lùi ngày** một hồ sơ | Neo gốc cây vào Bitcoin bằng OpenTimestamps 2 lần/ngày (`ops/ots_anchor.py`); gốc đã neo lệch sổ → trang hồ sơ báo đỏ | Hồ sơ mới chưa tới lượt neo (≤ 12 giờ + thời gian xác nhận khối) |
| T | Ảnh thực địa bị thay sau khi đóng băng vào hồ sơ | SHA-256 ảnh gốc + ảnh thu nhỏ trong nội dung ký; phép kiểm "evidence" | — |
| T | Sửa số đo cảm biến trong CSDL | Lưu nguyên chuỗi đã ký + chữ ký; bản xuất kiểm được bằng khoá công khai thiết bị | — |
| T | LLM bịa số trong lời diễn giải | Rào chắn con số: câu có số không nằm trong bằng chứng nó dẫn bị loại cả câu — `services/narrative.py`, `tests/test_gd4_evidence.py` | Sai về chữ (không phải số) vẫn có thể lọt — lời diễn giải không nằm trong phần ký |
| **R**epudiation | Chối đã phát hành / đã sửa | Nhật ký kiểm toán (`audit_log`): đăng nhập, đổi/đặt lại mật khẩu, tạo/thu hồi khoá API, đổi đồng ý, bật/tắt 2FA, dùng mã khôi phục | Nhật ký nằm trong cùng CSDL |
| **I**nformation disclosure | Lộ toạ độ thửa của người khác | Mã hồ sơ 12 ký tự ngẫu nhiên (~60 bit); sổ công khai chỉ có mã băm; tiết lộ chọn lọc bằng cam kết | Ai có mã hồ sơ thì xem được (thiết kế: chia sẻ mã = chia sẻ quyền xem) |
| I | Lộ bí mật khi xuất dữ liệu | Xuất tài khoản bỏ hash mật khẩu, hash khoá API, bí mật/mã khôi phục TOTP | — |
| I | Lộ khoá/bí mật trong kho công khai | `.gitignore` các tệp khoá; secret chỉ ở Render/GitHub Secrets; sao lưu CSDL mã hoá | Sai sót của người — kiểm trước mỗi commit |
| I | Tin đăng bán đất người dùng dán | Không lưu nội dung; chỉ nhận chữ người dùng tự dán, không cào trang bất động sản | — |
| I | Header lộ phiên bản | CSP, HSTS, nosniff, X-Frame-Options/frame-ancestors trên web và API; tắt `X-Powered-By`; **OWASP ZAP baseline** hằng ngày (`.zap/rules.tsv`, job `zap` trong `e2e-prod.yml`) | CSP còn `unsafe-inline` cho script (Next.js) |
| **D**enial of service | Đốt hạn mức nguồn mở | Cache theo URL/ô lưới, hạn mức theo IP/tài khoản cho thao tác nặng (`services/quota.py`), hàng đợi việc bền | Gói miễn phí Render ngủ sau 15 phút |
| D | Dò mã 2FA | 5 lần/15 phút/tài khoản (không tắt được bằng biến môi trường) | — |
| **E**levation of privilege | Người dùng thường vào mục quản trị | `require_admin` (403), vai trò nâng theo `TERRATWIN_ADMIN_EMAILS` khi đăng nhập, không tự hạ — `tests/test_roles.py` | — |
| E | Thư viện có lỗ hổng đã công bố | `pip-audit` + `npm audit --audit-level=high` trên mỗi push (job `security` trong `ci.yml`) | Lỗ hổng chưa công bố |
| E | Mô hình AI chưa kiểm định được bật | Kỷ luật đăng ký trước: ngưỡng viết trước, chấm một lần, trượt thì công khai và không bật | — |

## 5. Việc còn lại (theo thứ tự)

1. Chủ dự án bật 2FA cho tài khoản quản trị, rồi đặt `TERRATWIN_ADMIN_REQUIRE_2FA=1` trên Render.
2. Khi có khách doanh nghiệp: bắt buộc 2FA cho tài khoản có khoá API gói trả phí.
3. Thay `unsafe-inline` trong CSP bằng nonce khi Next.js hỗ trợ ổn định cho trang tĩnh.
4. Đổi mật khẩu ứng dụng Gmail (SMTP) định kỳ; khi cần xoay `TERRATWIN_SIGNING_KEY`, làm như
   mục khoá ký trong `DEPLOY.md` (khoá công khai cũ được giữ, hồ sơ cũ vẫn kiểm được).
5. Kiểm thử xâm nhập chủ động (ZAP full scan) trên một bản sao CSDL thử — không chạy trên production.
