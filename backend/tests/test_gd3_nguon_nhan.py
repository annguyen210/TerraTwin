"""Kiểm 20/11/2026 (/admin → Tin đăng GĐ3): 100 tin lần 6–9 lưu nguồn "nhãn người (chủ dự án…)" từ trước đính chính 00c9560.
Hiển thị phải là "nhãn Claude (đính chính 00c9560)"; nội dung tin và nhãn người thật (lần 10–12) giữ nguyên."""
from app.routes_admin import gold_note

THAT = [  # đúng 4 dạng đọc từ production 20/11/2026
    "GĐ3 lần 6 · tin 1 · Nghệ An · trang FB công khai môi giới · nhãn người (chủ dự án)",
    "GĐ3 lần 7 · tin 3 · Huế · trang FB công khai môi giới · nhãn người (chủ dự án)",
    "GĐ3 lần 8 · tin 12 · Cà Mau · trang FB công khai môi giới · nhãn người (chủ dự án)",
    "GĐ3 lần 9 · tin 30 · Sóc Trăng · trang FB công khai môi giới · nhãn người (chủ dự án tự gán; nhãn AI đã hiện trước khi gán)",
]


def test_lan_6_den_9_thanh_nhan_claude():
    for n in THAT:
        out = gold_note(n)
        assert out.endswith("nhãn Claude (đính chính 00c9560)") and "nhãn người" not in out
        assert out.split(" · nhãn")[0] == n.split(" · nhãn")[0]          # phần mô tả tin giữ nguyên


def test_nhan_nguoi_that_va_ghi_chu_khac_giu_nguyen():
    for n in ("GĐ3 lần 10 · tin 2 · nhãn người (chủ dự án)", "GĐ3 lần 12 · tin 5 · nhãn người độc lập",
              "tin bạn gửi", "", None):
        assert gold_note(n) == (n or "")
