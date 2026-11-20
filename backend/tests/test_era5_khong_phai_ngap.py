"""Kiểm 20/11/2026 trên fd89ebd: /plot/20.97160,106.28340 dòng đầu ghi "15 lần ngập lụt chạm ngưỡng nguy hiểm trong 10 năm"
ngay trên "vệ tinh thấy nước phủ thửa này 5 lần"; trợ lý "Thửa này từng ngập chưa?" trả "15 đợt lũ/ngập". Con số 15 là đợt
CHỈ SỐ MƯA ERA5 vượt ngưỡng — không phải lần ngập. Ngập quan sát được lấy từ radar Sentinel-1."""
from __future__ import annotations

import pytest

HIST = {"flood": {"name": None, "events": 15, "peak_month": 8, "peak_month_events": 6, "latest": "2026-08-23",
                  "worst_value": 80.0, "worst_date": "2020-10-10", "national_threshold": 40.0}}
WATER = {"cached": True, "available": True, "n_events": 5, "first": "2017-01-01", "last": "2026-11-01",
         "last_event": "2025-10-01"}


@pytest.fixture()
def gia(monkeypatch):
    from app.services import cache_store, passport, reqlang, water_history
    reqlang.set_lang("vi")
    h = {k: {**v, "name": passport._ten(k)} for k, v in HIST.items()}
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: h)
    monkeypatch.setattr(passport, "terrain", lambda lat, lon: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: dict(WATER))
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds: None)
    return passport


def test_dong_dau_khong_goi_era5_la_lan_ngap(gia):
    d = gia.build(20.9716, 106.2834)
    head = d["headline"]
    assert "lần ngập" not in head.replace("không phải lần ngập", "") and "ngập lụt" not in head
    assert "radar Sentinel-1 thấy nước phủ thửa 5 lần" in head            # ngập quan sát được đứng trước
    assert "15 đợt mưa lớn dễ gây ngập" in head and "ERA5" in head
    assert head.index("radar") < head.index("15 đợt")


def test_tro_ly_tra_loi_ngap_bang_so_radar(gia):
    from app.services import copilot
    from app.schemas import Location
    facts = copilot._history_facts(Location(lat=20.9716, lon=106.2834), ["flood"])
    assert "radar Sentinel-1 (quan sát thật): 5 đợt" in facts
    assert "Lũ/ngập" not in facts and "đợt lũ/ngập" not in facts.lower()
    assert "chỉ số thời tiết ERA5" in facts and "KHÔNG phải số lần xảy ra đo được" in facts
    assert "radar" in copilot._system().lower() and "ERA5" in copilot._system()


def test_lich_su_null_thi_noi_ly_do(monkeypatch):
    from app.services import cache_store, passport, reqlang, water_history
    reqlang.set_lang("vi")
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: None)
    monkeypatch.setattr(passport, "terrain", lambda lat, lon: {"elevation_m": 3, "lower_than_pct": 60, "radius_km": 3,
                                                               "slope_deg": 0.1, "meaning": "x"})
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"cached": False})
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds: None)
    d = passport.build(20.9716, 106.2834)
    assert d["history"] is None and "hết lượt" in d["history_note"]
