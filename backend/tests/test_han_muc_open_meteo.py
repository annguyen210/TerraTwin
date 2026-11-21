"""Kiểm A–Z 21/11/2026, P1-2 — chịu được hạn mức Open-Meteo miễn phí.

Một người gọi liên tục 18 mô-đun là api.open-meteo.com và archive-api.open-meteo.com cùng "exhausted"; khí hậu 10 năm
(archive) không có dự phòng → sạt lở Sa Pa 22.3364,103.8438 và Mù Cang Chải 21.85,104.09 "Chưa kết luận được"."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.services import realdata


def test_era5_lich_su_gom_theo_o_0_1_do(monkeypatch):
    seen = []
    monkeypatch.setattr(realdata, "_get", lambda url, timeout=15.0, **k: seen.append(url) or None)
    realdata.historical_weather(22.3364, 103.8438, "2015-01-01", "2024-12-31")
    realdata.historical_weather(22.3012, 103.8101, "2015-01-01", "2024-12-31")     # cách ~4 km — cùng ô
    assert "latitude=22.3&longitude=103.8" in seen[0] and seen[0] == seen[1]
    assert realdata._snap_clim(21.85) in (21.8, 21.9) and realdata._snap_clim(104.09) == 104.1


def test_phao_cuu_sinh_khi_hau_1_nam():
    ttl, stale = realdata._ttl_for("https://archive-api.open-meteo.com/v1/archive?latitude=22.3")
    assert ttl == 30 * 86400 and stale == 365 * 86400
    # dự báo không đổi chính sách
    assert realdata._ttl_for("https://api.open-meteo.com/v1/forecast?x")[1] == 24 * 3600


def test_bi_chan_thi_dung_ban_cu_toi_1_nam(monkeypatch):
    from app.services import cache_store
    url = "https://archive-api.open-meteo.com/v1/archive?latitude=21.9&longitude=104.1&test=phao"
    cache_store.put(realdata._cache_key(url), {"at": time.time() - 200 * 86400, "data": {"daily": "cu"}}, 365 * 86400)
    monkeypatch.setattr(realdata, "_fetch", lambda *a, **k: None)          # archive đang bị chặn
    assert realdata._get(url) == {"daily": "cu"}


def test_gian_nhip_goi_archive(monkeypatch):
    t = {"now": 1000.0}; ngu = []
    monkeypatch.setattr(realdata.time, "time", lambda: t["now"])
    monkeypatch.setattr(realdata.time, "sleep", lambda s: ngu.append(s) or t.__setitem__("now", t["now"] + s))
    monkeypatch.setattr(realdata, "ARCHIVE_GAP", 1.5)
    realdata._pace_last["archive"] = 0.0
    realdata._pace("https://archive-api.open-meteo.com/v1/archive?a")
    realdata._pace("https://archive-api.open-meteo.com/v1/archive?b")      # ngay sau → phải chờ 1,5 s
    realdata._pace("https://api.open-meteo.com/v1/forecast?c")             # dự báo không giãn
    assert ngu == [1.5]


def test_bi_chan_thi_noi_qua_tai_va_so_phut(monkeypatch):
    from app.modules import registry, util
    from app.schemas import Location
    from app.services import reqlang
    reqlang.set_lang("vi")
    monkeypatch.setattr(realdata, "blocked_minutes", lambda host: 7 if host.startswith("archive-api") else None)
    a = util.uncalibrated_assessment(registry.get_module("landslide"), Location(lat=22.3364, lon=103.8438))
    assert "quá tải" in a.recommendation and "7 phút" in a.recommendation
    monkeypatch.setattr(realdata, "blocked_minutes", lambda host: None)
    a = util.uncalibrated_assessment(registry.get_module("landslide"), Location(lat=22.3364, lon=103.8438))
    assert a.recommendation == "Thử lại sau ít phút."


def test_blocked_minutes_doc_ban_ghi_429(monkeypatch):
    from app.services import cache_store
    host = "archive-api.open-meteo.com"
    cache_store.put(realdata._quota_key(host), {"last": time.time(), "until": time.time() + 400, "wait": 400, "streak": 2,
                                                 "log": []}, 3600)
    assert realdata.blocked_minutes(host) == 7
    cache_store.put(realdata._quota_key(host), {"last": time.time() - 5000, "until": time.time() - 10, "log": []}, 3600)
    assert realdata.blocked_minutes(host) is None


import pytest


@pytest.mark.goi_overpass_that      # dùng _query THẬT; _fetch (mạng) vẫn bị giả lập ở dưới
def test_overpass_khong_tra_loi_thi_dung_ban_90_ngay(monkeypatch):
    from app.services import cache_store, osm
    q = "[out:json];node(1,2,3,4);out;  /* test phao */"
    cache_store.put(cache_store.make_key("osm-old", q), {"elements": ["cu"]}, 90 * 86400)
    monkeypatch.setattr(osm, "_fetch", lambda q: None)
    assert osm._query(q) == {"elements": ["cu"]}


def test_doc_san_khi_hau_cron(monkeypatch):
    from app.main import app
    from app.services import calibration
    monkeypatch.setenv("TERRATWIN_CRON_KEY", "cron-khi-hau")
    goi = []
    monkeypatch.setattr(calibration, "climatology", lambda mid, la, lo, **k: goi.append((mid, la, lo)) or [1.0])
    import threading
    monkeypatch.setattr(threading, "Thread", lambda target, **k: type("T", (), {"start": lambda self: target()})())
    with TestClient(app) as c:
        assert c.post("/api/climate/warm").status_code == 401
        r = c.post("/api/climate/warm", headers={"X-Cron-Key": "cron-khi-hau"}).json()
    from app.services import demo_plots
    assert r["queued_points"] >= len({(round(a, 2), round(b, 2)) for a, b, _ in demo_plots.DEMO_PLOTS})
    assert r["archive_cells"] <= r["queued_points"]
    assert {m for m, _, _ in goi} == {"flood", "landslide", "drought", "wildfire", "rain7"}
