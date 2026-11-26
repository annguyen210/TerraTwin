"""26/11/2026 — /metrics định dạng Prometheus: cần khoá cron/admin; đếm theo MẪU route, không lộ toạ độ."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import metrics


def test_can_khoa(monkeypatch):
    c = TestClient(app)
    assert c.get("/metrics").status_code == 401
    monkeypatch.setenv("TERRATWIN_CRON_KEY", "k-123")
    assert c.get("/metrics", headers={"X-Cron-Key": "sai"}).status_code == 401


def test_dinh_dang_va_mau_route(monkeypatch):
    monkeypatch.setenv("TERRATWIN_CRON_KEY", "k-123")
    c = TestClient(app)
    c.get("/api/high-ground?lat=99&lon=99")                 # 422 — toạ độ ngoài VN, không gọi mạng
    r = c.get("/metrics", headers={"X-Cron-Key": "k-123"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    t = r.text
    assert '# TYPE terratwin_http_requests_total counter' in t
    assert 'route="/api/high-ground",method="GET",status="422"' in t
    assert "lat=99" not in t and "99" not in t.split("terratwin_http_requests_total")[1].split("\n")[0]
    assert 'terratwin_http_request_duration_seconds_bucket{route="/api/high-ground",le="+Inf"}' in t


def test_histogram_cong_don():
    metrics.observe("/x", "GET", 200, 0.2)
    metrics.observe("/x", "GET", 200, 3.0)
    t = metrics.render()
    assert 'terratwin_http_request_duration_seconds_bucket{route="/x",le="0.25"} 1' in t
    assert 'terratwin_http_request_duration_seconds_count{route="/x"} 2' in t
