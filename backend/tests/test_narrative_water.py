"""Câu "Lịch sử nước radar" trong lời diễn giải — mọi nhánh (17/10/2026: chèn cảnh báo mặt nước hôm 16/10 làm câu
0 đợt bình thường thành "thấy nước phủ thửa 0 đợt" — lỗi cấu trúc if/else, không test nào bắt)."""
from app.services import narrative

BASE = {"n_scenes": 327, "first": "2017-01-04", "last": "2026-10-10", "events": []}


def _text(**w):
    return narrative.template_sentences({"water_history_radar": {**BASE, **w}}, {"water.summary": {}})[0]["text"]


def test_khong_dot_nao_thi_noi_chua_thay_nuoc():
    t = _text(n_events=0)
    assert t.startswith("Radar Sentinel-1 chưa thấy nước phủ thửa lần nào trong 327 cảnh") and "0 đợt" not in t


def test_co_dot_thi_noi_so_dot_va_dot_gan_nhat():
    t = _text(n_events=2, events=[{"start": "2020-10-10"}, {"start": "2025-11-01"}])
    assert "thấy nước phủ thửa 2 đợt" in t and "2025-11-01" in t


def test_khu_do_thi_khong_noi_chua_tung_ngap():
    t = _text(n_events=0, urban={"built_pct": 86.0, "source": "ESA WorldCover 2021"})
    assert "khu đô thị" in t and "KHÔNG có nghĩa là không ngập" in t and "chưa thấy nước phủ" not in t


def test_khung_do_co_mat_nuoc_them_luu_y_vao_cau_dung():
    t = _text(n_events=0, water_surface={"share": "≥10%", "pct": 10, "baseline_db": -19.11})
    assert t.startswith("Radar Sentinel-1 chưa thấy nước phủ thửa lần nào") and "≥10% khung đo là mặt nước thường xuyên" in t
