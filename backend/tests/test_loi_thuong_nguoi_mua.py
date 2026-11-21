"""Kiểm A–Z 21/11/2026, P2-1 — lớp "nói dễ hiểu": khối lịch sử nước có 1 câu + 3 gạch đầu dòng lời thường (đã từng có nước
phủ mấy lần · lần nặng nhất · nghĩa là gì với người mua, nên hỏi ai). Giữ nguyên số liệu, không thêm phép đo."""
from app.services import reqlang, water_history


def _r(**k):
    base = {"available": True, "first": "2017-01-03", "n_scenes": 284, "events": [], "n_events": 0}
    base.update(k)
    return base


def test_co_dot_nuoc():
    reqlang.set_lang("vi")
    ev = [{"start": "2020-10-12", "end": "2020-10-24", "n_scenes": 2, "peak_cover": "45%", "season": "in"},
          {"start": "2024-09-12", "end": "2024-09-12", "n_scenes": 1, "peak_cover": "92%", "season": "in"},
          {"start": "2025-10-01", "end": "2025-10-01", "n_scenes": 1, "peak_cover": "30%", "season": "in"}]
    p = water_history.plain_points(_r(events=ev, n_events=3, n_in=3, n_out=0))
    assert len(p) == 3
    assert p[0].startswith("Đã từng có nước phủ thửa: 3 lần từ 2017") and "1/10/2025" in p[0]
    assert "Lần nặng nhất: 12/9/2024 — nước phủ 92% thửa" in p[1]          # số giữ nguyên
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
