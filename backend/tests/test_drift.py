"""A14 — PSI phát hiện trôi; trôi hiệu năng; endpoint /api/admin/drift."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import drift


def test_psi_identical_is_near_zero():
    xs = list(range(100))
    assert drift.psi(xs, xs) < 0.05


def test_psi_flags_a_shifted_distribution():
    base = list(range(100))
    shifted = [x + 60 for x in range(100)]     # dịch mạnh lên
    assert drift.psi(base, shifted) > drift.PSI_ALERT


def test_psi_not_enough_data_returns_zero():
    assert drift.psi([1, 2, 3], [1]) == 0.0


def test_performance_drift_structure():
    # DB dùng chung giữa các test → KHÔNG giả định nó trống. Chỉ khẳng định các
    # BẤT BIẾN đúng với mọi trạng thái dữ liệu.
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        d = drift.performance_drift(db)
        assert d["module_id"] == "all"
        assert isinstance(d["degraded"], bool) and isinstance(d["enough"], bool)
        # Bất biến cốt lõi: chưa đủ dữ liệu thì KHÔNG được coi là "trôi".
        if not d["enough"]:
            assert d["degraded"] is False
    finally:
        db.close()


def test_drift_endpoint_requires_login():
    with TestClient(app) as c:
        assert c.get("/api/admin/drift").status_code == 401


def test_drift_endpoint_returns_overview():
    with TestClient(app) as c:
        c.post("/api/auth/register",
               json={"email": "drift@x.com", "password": "Passw0rd1", "name": "D"})
        tok = c.post("/api/auth/login",
                     json={"email": "drift@x.com", "password": "Passw0rd1"}).json()["access_token"]
        r = c.get("/api/admin/drift", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        body = r.json()
        assert "overall" in body and "by_module" in body
        assert isinstance(body["degraded_modules"], list)
