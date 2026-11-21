"""Kiểm A–Z 21/11/2026, P1-7 — cảnh báo nhiễu làm mất tin tưởng.

Đo trên bản chính thức (quét sâu 10 thửa, trước khi sửa): 18 cảnh báo, trong đó 9 "ngập úng đô thị" (ruộng lúa Quảng Điền
bê tông 9,3%; Đông Anh "chảy tràn 0 mm so với 0 mm"; Bảo Lộc 11 mm) và 2 "ao nuôi" trên thửa ĐẤT (Hội An, Hoàn Lão: "sóng
cao 2.2–2.3 m — gia cố lồng bè")."""
from __future__ import annotations

import pytest

from app.modules.registry import get_module
from app.schemas import Location
from app.services import datasources as ds, landuse, osm, realdata, water_history


def _wc(monkeypatch, built: float):
    monkeypatch.setattr(osm, "built_environment", lambda *a, **k: None)
    monkeypatch.setattr(landuse, "composition", lambda la, lo, radius_m=None: {
        "source": "ESA WorldCover 2021 v200 (10 m)", "year": "2021",
        "group_pct": {"built": built, "tree": 5.0, "crop": 95.0 - built, "water": 0.0}})


def test_ruong_lua_it_be_tong_thi_do_thi_khong_ap_dung(monkeypatch):
    _wc(monkeypatch, 9.3)                                   # Quảng Điền
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (168.7, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 2.0)
    a = get_module("urban").assess(Location(lat=16.5751, lon=107.4952))
    assert a.status == "out_of_scope" and a.risk_level == "unknown" and a.is_real is False
    assert "chưa đô thị hoá" in a.headline and "9.3%" in a.headline


def test_chay_tran_tang_it_thi_khong_canh_bao(monkeypatch):
    _wc(monkeypatch, 33.1)                                  # Đông Anh: 6,9 mm mưa → chảy tràn tăng ~0 mm
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (6.9, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 8.0)
    a = get_module("urban").assess(Location(lat=21.1405, lon=105.8468))
    assert a.status == "ok" and a.risk_level == "safe"
    _wc(monkeypatch, 69.7)                                  # Bảo Lộc: 28,5 mm mưa → tăng ~10 mm
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (28.5, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 850.0)
    assert get_module("urban").assess(Location(lat=11.548, lon=107.807)).risk_level == "safe"


def test_do_thi_mua_lon_that_van_canh_bao(monkeypatch):
    _wc(monkeypatch, 62.2)                                  # Hội An: 192,8 mm mưa → chảy tràn tăng rất lớn
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (192.8, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 3.0)
    a = get_module("urban").assess(Location(lat=15.8794, lon=108.327))
    assert a.risk_level in ("warning", "danger") and a.metrics["chay_tran_mm"] - a.metrics["chay_tran_tu_nhien_mm"] >= 20


def _marine(sst, wave):
    return {"sst_max": sst, "sst_min": sst - 1, "wave_max": wave, "forecast": [], "days": 7}


def test_thua_dat_ven_bien_khong_nhan_canh_bao_ao_nuoi(monkeypatch):
    monkeypatch.setattr(water_history, "pond", lambda la, lo: {"water_pct": 3.0})
    monkeypatch.setattr(ds, "marine_context", lambda la, lo: _marine(28.6, 2.3))
    a = get_module("aquaculture").assess(Location(lat=15.8794, lon=108.327))
    assert a.status == "out_of_scope" and a.risk_level == "unknown" and "không có ao/lồng bè" in a.headline


def test_ao_that_van_canh_bao_song_lon(monkeypatch):
    monkeypatch.setattr(water_history, "pond", lambda la, lo: {"water_pct": 64.0})
    monkeypatch.setattr(ds, "marine_context", lambda la, lo: _marine(29.0, 2.6))
    a = get_module("aquaculture").assess(Location(lat=9.18, lon=105.09))
    assert a.status == "ok" and a.risk_level == "warning"


def test_khong_doc_duoc_worldcover_thi_ao_nuoi_chay_nhu_cu(monkeypatch):
    monkeypatch.setattr(water_history, "pond", lambda la, lo: None)
    monkeypatch.setattr(ds, "marine_context", lambda la, lo: _marine(29.0, 2.6))
    assert get_module("aquaculture").assess(Location(lat=9.18, lon=105.09)).risk_level == "warning"


@pytest.mark.do_thi_that      # dùng water_history.pond THẬT (WorldCover giả lập ở dưới)
def test_pond_doc_ma_mat_nuoc_worldcover(monkeypatch):
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo, r: {"hist": {"80": 30, "90": 10, "40": 60}})
    assert water_history.pond(1.0, 2.0) == {"water_pct": 40.0}
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo, r: None)
    assert water_history.pond(1.0, 2.0) is None
