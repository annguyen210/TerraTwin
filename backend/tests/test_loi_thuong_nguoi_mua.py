"""Kiểm A–Z 21/11/2026, P2-1 — lớp "nói dễ hiểu": khối lịch sử nước có 1 câu + 3 gạch đầu dòng lời thường (đã từng có nước
phủ mấy lần · lần nặng nhất · nghĩa là gì với người mua, nên hỏi ai). Giữ nguyên số liệu, không thêm phép đo."""
from app.services import reqlang, water_history


def _r(**k):
    base = {"available": True, "first": "2017-01-03", "n_scenes": 284, "events": [], "n_events": 0}
    base.update(k)
    return base


def test_co_dot_nuoc():
    reqlang.set_lang("vi")
    ev = [{"start": "2020-10-12", "end": "2020-10-24", "n_scenes": 2, "peak_cover": "25–50%", "season": "in"},
          {"start": "2024-09-12", "end": "2024-09-12", "n_scenes": 1, "peak_cover": "≥50%", "season": "in"},
          {"start": "2025-10-01", "end": "2025-10-01", "n_scenes": 1, "peak_cover": "10–25%", "season": "in"}]
    p = water_history.plain_points(_r(events=ev, n_events=3, n_in=3, n_out=0))
    assert len(p) == 3
    assert p[0].startswith("Đã từng có nước phủ thửa: 3 lần từ 2017") and "1/10/2025" in p[0]
    assert "Lần nặng nhất: 12/9/2024 — nước phủ ≥50% thửa" in p[1]          # số giữ nguyên
    assert "Hỏi người bán và hàng xóm" in p[2] and "UBND xã" in p[2]


def test_chua_thay_nuoc_khong_noi_chac_chan():
    reqlang.set_lang("vi")
    p = water_history.plain_points(_r())
    assert "Chưa thấy nước phủ thửa trong 284 ảnh radar từ 2017" in p[0]
    assert "không có nghĩa là chắc chắn không ngập" in p[1]


def test_do_thi_khong_ket_luan():
    reqlang.set_lang("vi")
    p = water_history.plain_points(_r(urban={"built_pct": 86.0, "note": "x"}))
    assert "KHÔNG kết luận được" in p[0] and "KHÔNG có nghĩa là không ngập" in p[1]


def test_khong_co_du_lieu_thi_khong_co_gach():
    assert water_history.plain_points({"available": False}) is None


def test_lan_nang_nhat_theo_nac_phu_khong_theo_so_anh():
    """Kiểm 22/11/2026 trên bản chính thức: mức phủ là nấc "10–25%" / "25–50%" / "≥50%" — đợt ≥50% (1 ảnh) phải nặng hơn
    đợt 25–50% (3 ảnh)."""
    reqlang.set_lang("vi")
    ev = [{"start": "2017-07-27", "end": "2017-08-08", "n_scenes": 3, "peak_cover": "25–50%", "season": "in"},
          {"start": "2024-09-12", "end": "2024-09-12", "n_scenes": 1, "peak_cover": "≥50%", "season": "in"},
          {"start": "2025-10-01", "end": "2025-10-01", "n_scenes": 2, "peak_cover": "10–25%", "season": "in"}]
    p = water_history.plain_points(_r(events=ev, n_events=3, n_in=3, n_out=0))
    assert p[1].startswith("Lần nặng nhất: 12/9/2024 — nước phủ ≥50% thửa")


def test_nhieu_dot_cung_nac_cao_nhat_thi_ke_du():
    """Tuệ Tĩnh trên bản chính thức (22/11/2026): 3 đợt cùng ≥50% — không được chọn bừa một đợt làm "lần nặng nhất"."""
    reqlang.set_lang("vi")
    ev = [{"start": "2017-07-27", "end": "2017-08-08", "n_scenes": 3, "peak_cover": "25–50%", "season": "in"},
          {"start": "2018-07-22", "end": "2018-07-22", "n_scenes": 1, "peak_cover": "≥50%", "season": "in"},
          {"start": "2024-07-26", "end": "2024-08-07", "n_scenes": 2, "peak_cover": "10–25%", "season": "in"},
          {"start": "2024-09-12", "end": "2024-09-12", "n_scenes": 1, "peak_cover": "≥50%", "season": "in"},
          {"start": "2025-10-01", "end": "2025-10-01", "n_scenes": 1, "peak_cover": "≥50%", "season": "in"}]
    p = water_history.plain_points(_r(events=ev, n_events=5, n_in=5, n_out=0))
    assert p[1] == "Mức nặng nhất — nước phủ ≥50% thửa — xảy ra 3 lần: 22/7/2018, 12/9/2024, 1/10/2025."
