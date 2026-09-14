"""M1 — Web Push: lưu đăng ký, khoá công khai, an toàn khi chưa cấu hình VAPID."""
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.services import push


def _token(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "Passw0rd1", "name": "P"})
    return c.post("/api/auth/login", json={"email": email, "password": "Passw0rd1"}).json()["access_token"]


def test_key_endpoint_unconfigured_by_default(monkeypatch):
    monkeypatch.delenv("TERRATWIN_VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("TERRATWIN_VAPID_PRIVATE_KEY", raising=False)
    with TestClient(app) as c:
        r = c.get("/api/push/key")
        assert r.status_code == 200
        assert r.json()["configured"] is False


def test_subscribe_requires_login():
    with TestClient(app) as c:
        assert c.post("/api/push/subscribe", json={}).status_code == 401


def test_subscribe_valid_and_invalid():
    with TestClient(app) as c:
        tok = _token(c, "push1@x.com")
        H = {"Authorization": f"Bearer {tok}"}
        bad = c.post("/api/push/subscribe", json={"endpoint": "x"}, headers=H)
        assert bad.status_code == 422        # thiếu keys
        good = c.post("/api/push/subscribe", json={
            "endpoint": "https://push.example/abc",
            "keys": {"p256dh": "BKxx", "auth": "aabb"},
        }, headers=H)
        assert good.status_code == 204


def test_send_to_user_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TERRATWIN_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("TERRATWIN_VAPID_PUBLIC_KEY", raising=False)
    assert push.configured() is False
    db = SessionLocal()
    try:
        assert push.send_to_user(db, 1, "t", "b") == 0   # không cấu hình → 0, không ném
    finally:
        db.close()
