"""Kiểm A–Z 24/11/2026.

1) Giữa thị trấn Ba Tri (10.04427, 106.5902 — WorldCover 97,9% bề mặt xây dựng) vẫn ra "sâu bệnh: bình thường",
   "năng suất: ổn định", "≈42.48 ha có rừng, 16339.85 tCO₂" → khu nhà cửa: KHÔNG ÁP DỤNG.
2) Thửa demo Tuệ Tĩnh (20.9716, 106.2834): năng suất "nguy hiểm" vì NDVI nay 0,196 < 0,20, dù đỉnh 180 ngày chỉ 0,245
   (chưa từng thấy vụ cây rõ) → chưa kết luận được, không báo đỏ."""
from __future__ import annotations

import pytest

from app.modules import group_a
from app.modules.registry import get_module
from app.schemas import Location
from app.services import optical, reqlang

BA_TRI = Location(lat=10.04427, lon=106.5902)
TUE_TINH = Location(lat=20.9716, lon=106.2834)


@pytest.mark.parametrize("mid", ["pest", "yield", "carbon"])
def test_khu_nha_cua_khong_ap_dung(monkeypatch, mid):
    reqlang.set_lang("vi")
    monkeypatch.setattr(group_a, "_built_up", lambda loc: 97.9)
    def _khong_duoc_goi(*a, **k):
        raise AssertionError("khu nhà cửa: không được đọc chuỗi ảnh vệ tinh")
    monkeypatch.setattr(optical, "stress", _khong_duoc_goi)
    monkeypatch.setattr(optical, "growth", _khong_duoc_goi)
    a = get_module(mid).assess(BA_TRI)
    assert a.status == "out_of_scope" and a.risk_level == "unknown"
    assert a.headline.startswith("Không áp dụng — khu nhà cửa (97.9% bề mặt xây dựng")
    assert "tCO" not in a.headline


@pytest.mark.doc_worldcover_that
def test_nguong_khu_nha_cua_doc_tu_khung_worldcover(monkeypatch):
    from app.services import water_history
    monkeypatch.setattr(water_history, "_frame_pct", lambda lat, lon: {50: 97.9, 10: 2.1})
    assert group_a._built_up(BA_TRI) == 97.9
    monkeypatch.setattr(water_history, "_frame_pct", lambda lat, lon: {50: 35.0, 40: 65.0})   # làng ven ruộng
    assert group_a._built_up(TUE_TINH) is None
    monkeypatch.setattr(water_history, "_frame_pct", lambda lat, lon: None)                     # không đọc được
    assert group_a._built_up(TUE_TINH) is None


def _growth(now, peak, harvest=False):
    return {"applicable": True, "ndvi_now": now, "ndvi_peak": peak, "peak_date": "2026-06-21", "stage": "đất trống / vừa thu hoạch",
            "harvest": harvest, "days_since_peak": 150, "ndvi_integral": 10.0, "vigor_vs_peak_pct": 80.0,
            "method": "NDVI.", "caveat": "", "advice": "", "cover": "đất trống"}


def test_nang_suat_chua_tung_co_vu_ro_thi_khong_bao_do(monkeypatch):
    reqlang.set_lang("vi")
    monkeypatch.setattr(optical, "growth", lambda lat, lon: _growth(0.1961, 0.2452))
    a = get_module("yield").assess(TUE_TINH)
    assert a.risk_level == "unknown" and a.headline.startswith("Chưa kết luận được")


def test_nang_suat_mat_vu_that_van_bao_do(monkeypatch):
    reqlang.set_lang("vi")
    monkeypatch.setattr(optical, "growth", lambda lat, lon: _growth(0.15, 0.78))
    assert get_module("yield").assess(TUE_TINH).risk_level == "danger"
    monkeypatch.setattr(optical, "growth", lambda lat, lon: _growth(0.15, 0.78, harvest=True))
    assert get_module("yield").assess(TUE_TINH).risk_level == "safe"


def test_tieu_de_carbon_lam_tron_3_chu_so(monkeypatch):
    from app.services import mrv, sentinel
    reqlang.set_lang("vi")
    monkeypatch.setattr(sentinel, "index_distribution", lambda *a, **k: {"area_ha": 144.0, "mean": 0.5, "std": 0.1,
                        "coverage_pct": 98.0, "observed_window": "2026-10-01/2026-11-20", "pixel_m": 10})
    monkeypatch.setattr(sentinel, "fraction_above", lambda d, thr: 0.295)
    r = mrv.build(11.5, 107.4)
    import re
    assert not re.search(r"\d+\.\d{2} tCO", r["headline"])      # không còn kiểu "16339.85 tCO₂"
    shown = re.search(r"khoảng ([\d.]+) tCO₂", r["headline"]).group(1)
    assert len(shown.replace(".", "").rstrip("0")) <= 3          # 3 chữ số có nghĩa
    assert r["estimated"]["stock_tco2"] == round(r["estimated"]["stock_tco2"], 2)    # số đầy đủ (đã băm) giữ nguyên
