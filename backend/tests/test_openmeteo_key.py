"""Khoá Open-Meteo trả phí: chỉ chèn ở bước gửi đi, không vào khoá cache/log, health báo đúng gói."""
from __future__ import annotations


def test_khong_co_khoa_thi_url_giu_nguyen(monkeypatch):
    from app.services import openmeteo
    monkeypatch.delenv("TERRATWIN_OPENMETEO_API_KEY", raising=False)
    u = "https://api.open-meteo.com/v1/forecast?latitude=16.46&longitude=107.59"
    assert openmeteo.sign(u) == u
    assert openmeteo.plan()["plan"] == "free_non_commercial" and openmeteo.plan()["note"]


def test_co_khoa_thi_doi_sang_may_chu_khach_hang_va_them_apikey(monkeypatch):
    from app.services import openmeteo
    monkeypatch.setenv("TERRATWIN_OPENMETEO_API_KEY", "BI-MAT-123")
    s = openmeteo.sign("https://archive-api.open-meteo.com/v1/archive?latitude=1&longitude=2")
    assert s == "https://customer-archive-api.open-meteo.com/v1/archive?latitude=1&longitude=2&apikey=BI-MAT-123"
    assert openmeteo.sign("https://api.met.no/x?y=1") == "https://api.met.no/x?y=1"      # nguồn khác: không đụng
    assert openmeteo.redact("lỗi tại ...&apikey=BI-MAT-123") == "lỗi tại ...&apikey=***"
    assert openmeteo.plan() == {"plan": "commercial", "key_configured": True, "note": None}


def test_khoa_khong_lot_vao_khoa_cache_va_duoc_chen_khi_goi_mang(monkeypatch):
    from app.services import realdata
    monkeypatch.setenv("TERRATWIN_OPENMETEO_API_KEY", "BI-MAT-123")
    u = "https://api.open-meteo.com/v1/elevation?latitude=16.46&longitude=107.59"
    assert "BI-MAT-123" not in realdata._cache_key(u)
    seen = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"elevation":[5]}'

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        return R()
    monkeypatch.setattr(realdata.urllib.request, "urlopen", fake_urlopen)
    assert realdata._fetch(u, 5) == {"elevation": [5]}
    assert seen["url"].startswith("https://customer-api.open-meteo.com/") and seen["url"].endswith("&apikey=BI-MAT-123")


def test_health_bao_goi_du_lieu_thoi_tiet(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.delenv("TERRATWIN_OPENMETEO_API_KEY", raising=False)
    with TestClient(app) as c:
        h = c.get("/api/health").json()
    assert h["weather_data_plan"]["plan"] == "free_non_commercial" and "BI-MAT" not in str(h)
