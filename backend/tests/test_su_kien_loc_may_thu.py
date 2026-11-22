"""Kiểm A–Z lần 2 (22/11/2026): phễu sự kiện bị thổi phồng bởi máy chạy thử — /api/events bỏ qua User-Agent trình duyệt
không giao diện; /admin ghi rõ từ ngày nào mới lọc (không xoá số cũ)."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import Event, SessionLocal
from app.main import app


def _n():
    with SessionLocal() as s:
        return s.execute(select(func.count(Event.id)).where(Event.name == "open")).scalar_one()


def test_bo_qua_trinh_duyet_tu_dong():
    with TestClient(app) as c:
        n0 = _n()
        for ua in ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/131.0 Safari/537.36",
                   "Mozilla/5.0 Playwright/1.48"):
            assert c.post("/api/events", json={"name": "open"}, headers={"User-Agent": ua}).status_code == 204
        assert _n() == n0
        c.post("/api/events", json={"name": "open"},
               headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36"})
        assert _n() == n0 + 1


def test_pheu_ghi_ro_ngay_bat_dau_loc():
    from app.routes_data import funnel
    with SessionLocal() as s:
        r = funnel(days=30, user=None, db=s)
    assert r["filter_since"] == "2026-11-22" and "số trước đó gồm cả lượt thử" in r["filter_note"]
