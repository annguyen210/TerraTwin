"""M4 — bản tin sáng: soạn đúng, gửi theo opt-in, dedup theo ngày, toggle."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, User, Plot
from sqlalchemy import select
from app.services import brief


def _mk_user(email, with_plot=True, opted=False):
    db = SessionLocal()
    try:
        u = User(email=email, password_hash="x", name="B",
                 morning_brief=1 if opted else 0)
        db.add(u); db.commit(); db.refresh(u)
        if with_plot:
            db.add(Plot(user_id=u.id, name="R", lat=16.4, lon=107.5)); db.commit()
        return u.id
    finally:
        db.close()


def test_compose_safe_vs_alert():
    uid = _mk_user("brief_c@x.com", with_plot=True)
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        title, body = brief.compose(db, u)
        assert "bản tin sáng" in title
        assert "an toàn" in body            # chưa có cảnh báo → an toàn
    finally:
        db.close()


def test_compose_none_without_plot():
    uid = _mk_user("brief_np@x.com", with_plot=False)
    db = SessionLocal()
    try:
        assert brief.compose(db, db.get(User, uid)) is None
    finally:
        db.close()


def test_run_all_dedups_by_day():
    # Opt-in + có thửa. force=True để bỏ qua việc chưa cấu hình push.
    _mk_user("brief_r@x.com", with_plot=True, opted=True)
    db = SessionLocal()
    try:
        r1 = brief.run_all(db, force=True)
        assert r1["sent"] >= 1
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Lần 2 KHÔNG force → đã gửi hôm nay → skip.
        r2 = brief.run_all(db, force=False)
        assert r2["date"] == today
        u = db.execute(select(User).where(User.email == "brief_r@x.com")).scalar_one()
        assert u.brief_last == today
    finally:
        db.close()


def test_toggle_and_status_endpoints():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "brief_t@x.com", "password": "Passw0rd1", "name": "T"})
        tok = c.post("/api/auth/login", json={"email": "brief_t@x.com", "password": "Passw0rd1"}).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        assert c.get("/api/brief/status", headers=H).json()["enabled"] is False
        assert c.post("/api/brief/toggle?on=true", headers=H).json()["enabled"] is True
        assert c.get("/api/brief/status", headers=H).json()["enabled"] is True


def test_run_requires_admin():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "brief_u@x.com", "password": "Passw0rd1", "name": "U"})
        tok = c.post("/api/auth/login", json={"email": "brief_u@x.com", "password": "Passw0rd1"}).json()["access_token"]
        assert c.post("/api/brief/run", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
