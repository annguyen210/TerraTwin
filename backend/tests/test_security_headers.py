"""Header bảo mật trên MỌI phản hồi API, kể cả 429 (giới hạn tốc độ) và 413 (body quá lớn) — lỗi thật 18/10/2026:
OWASP ZAP baseline đỏ ngắt quãng vì phản hồi 429 thiếu Strict-Transport-Security."""
from __future__ import annotations

from fastapi.testclient import TestClient

HTTPS = {"X-Forwarded-Proto": "https"}


def _check(r, hsts=True):
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert ("strict-transport-security" in r.headers) is hsts


def test_phan_hoi_thuong_va_404_co_header():
    from app.main import app
    with TestClient(app) as c:
        _check(c.get("/api/health", headers=HTTPS))
        _check(c.get("/khong-co-trang-nay", headers=HTTPS))
        _check(c.get("/api/health"), hsts=False)              # HTTP thuần (máy dev) → không gửi HSTS


def test_429_gioi_han_toc_do_van_co_hsts(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "_RATE", 1)
    main._HITS.clear()
    with TestClient(main.app) as c:
        c.get("/api/health", headers=HTTPS)
        r = c.get("/api/health", headers=HTTPS)
    main._HITS.clear()
    assert r.status_code == 429
    _check(r)


def test_413_body_qua_lon_van_co_hsts():
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/scan", content=b"x" * (6 * 1024 * 1024),
                   headers={**HTTPS, "Content-Type": "application/json", "Content-Length": str(6 * 1024 * 1024)})
    assert r.status_code == 413
    _check(r)


def test_tai_lieu_api_khong_bi_csp_chan():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/docs", headers=HTTPS)
    assert "content-security-policy" not in r.headers and r.headers["x-frame-options"] == "DENY"
