"""THỬA DÙNG KHI DEMO — một danh sách cho mọi chỗ cần hâm nóng (16/10/2026, việc 3 kiểm toàn bộ).

Đọc lịch sử nước radar cho một thửa MỚI mất thường 1–3 phút (đo: 69 s và 181 s trên Render cho hai thửa khác nhau —
phụ thuộc số cảnh và tải máy chủ), loại đất AlphaEarth ~10–15 s. Hâm trước những thửa sẽ bấm khi demo để không ai
phải chờ. Kết quả lịch sử nước giữ 6 ngày; tác vụ radar.yml gọi POST /api/water/warm-demo mỗi 6 giờ — đã có thì
không tốn gì.
"""
from __future__ import annotations

DEMO_PLOTS: list[tuple[float, float, str]] = [
    # thửa mẫu trang đầu ("Xem ngay: Huế", "Kiểm một tin đăng")
    (16.5751, 107.4952, "Đồng lúa Quảng Điền, Huế"),
    # 8 nơi trong màn chọn nhanh (frontend/components/Start.tsx QUICK) — đất nông nghiệp / ven đô từ 17/10/2026
    (10.07, 106.57, "Bến Tre"), (9.18, 105.09, "Cà Mau"), (15.33, 108.05, "Trà Leng, Quảng Nam"),
    (16.52, 107.59, "Huế"), (11.56, 108.93, "Phan Rang"), (12.73, 108.05, "Buôn Ma Thuột"),
    (21.12, 105.89, "Hà Nội"), (22.36, 103.59, "Lai Châu"),
    # 5 thửa mẫu còn lại của nhật ký sống (plot_journal.SAMPLE_PLOTS)
    (10.0452, 105.7469, "Phong Điền, Cần Thơ"), (21.1405, 105.8468, "Đông Anh, Hà Nội"),
    (11.7536, 108.2190, "Lâm Hà, Lâm Đồng (cà phê)"), (9.0820, 104.9690, "Trần Văn Thời, Cà Mau"),
    (15.8890, 108.2500, "Điện Bàn, Quảng Nam"),
]
