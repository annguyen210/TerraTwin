"""A5 — nguồn gốc dữ liệu + tái lập cho một cảnh báo."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, User, Plot, Alert
from app.services import lineage


def _seed():
    db = SessionLocal()
    u = User(email=f"lin{datetime.now().timestamp()}@x.com", password_hash="x", name="L")
    db.add(u); db.commit(); db.refresh(u)
    p = Plot(user_id=u.id, name="R", lat=16.46, lon=107.59)
    db.add(p); db.commit(); db.refresh(p)
    a = Alert(user_id=u.id, plot_id=p.id, module_id="flood", risk_level="danger",
              headline="Nguy cơ ngập", recommendation="x", window_days=7,
              observed_peak=82.0, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(a); db.commit(); db.refresh(a)
    aid, uid = a.id, u.id
    db.close()
    return aid, uid


def test_lineage_has_sources_model_reproduce_and_hash():
    aid, _ = _seed()
    db = SessionLocal()
    try:
        lin = lineage.for_alert(db, aid)
    finally:
        db.close()
    assert lin["inputs"]["module_id"] == "flood"
    assert any("ERA5" in s for s in lin["sources"])
    assert lin["model"]["thresholds"]["warning"] == 70.0
    assert lin["reproduce"] is not None and "verify_api" in lin["reproduce"]
    assert len(lin["lineage_hash"]) == 64


def test_lineage_hash_is_deterministic():
    aid, _ = _seed()
    db = SessionLocal()
    try:
        a1 = lineage.for_alert(db, aid)
        a2 = lineage.for_alert(db, aid)
    finally:
        db.close()
    assert a1["lineage_hash"] == a2["lineage_hash"]


def test_endpoint_owner_only():
    aid, _ = _seed()
    with TestClient(app) as c:
        assert c.get(f"/api/explain/{aid}/lineage").status_code == 401
        # người KHÁC không xem được cảnh báo này.
        c.post("/api/auth/register", json={"email": "other@x.com", "password": "Passw0rd1", "name": "O"})
        tok = c.post("/api/auth/login", json={"email": "other@x.com", "password": "Passw0rd1"}).json()["access_token"]
        r = c.get(f"/api/explain/{aid}/lineage", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404
