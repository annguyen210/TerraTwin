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


def test_tro_ly_co_tung_dot_nuoc_de_tra_loi_theo_nam(gia, monkeypatch):
    """Kiểm A–Z 24/11/2026: hỏi "Ruộng này năm 2024 có bị ngập không?" → trợ lý trả "không có dữ liệu" vì ngữ cảnh chỉ có
    số đợt + đợt gần nhất (2025), dù radar thấy 26/7 và 12/9/2024 (bão Yagi). Ngữ cảnh phải có TỪNG đợt kèm mức phủ."""
    from app.services import copilot, water_history
    from app.schemas import Location
    evs = [{"start": "2018-07-22", "end": "2018-07-22", "cover": "≥50%"},
           {"start": "2024-07-26", "end": "2024-07-26", "cover": "10–25%"},
           {"start": "2024-09-12", "end": "2024-09-24", "cover": "≥50%"}]
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {**WATER, "n_events": 3, "events": evs})
    facts = copilot._history_facts(Location(lat=20.9716, lon=106.2834), ["flood"])
    assert "26/7/2024 (phủ 10–25% thửa)" in facts and "12/9/2024–24/9/2024 (phủ ≥50% thửa)" in facts
    sysp = copilot._system()
    assert "KHÔNG khuyên" in sysp and "'nhẹ'" in sysp


def test_tom_tat_luu_tung_dot_tu_bo_nho_dem(monkeypatch):
    from app.services import cache_store, flood_season, water_history
    monkeypatch.setattr(flood_season, "season_cached", lambda lat, lon: None)
    hit = {"available": True, "first": "2017-01-01", "last": "2026-11-01",
           "events": [{"start": "2024-09-12", "end": "2024-09-24", "peak_cover": "≥50%"},
                      {"start": "2018-07-22", "end": "2018-07-22", "peak_cover": "25–50%"}]}
    monkeypatch.setattr(cache_store, "get", lambda k: hit)
    s = water_history.summary(20.9716, 106.2834)
    assert s["n_events"] == 2 and s["last_event"] == "2024-09-12"
    assert [e["start"] for e in s["events"]] == ["2018-07-22", "2024-09-12"]
    assert s["events"][1] == {"start": "2024-09-12", "end": "2024-09-24", "cover": "≥50%"}
