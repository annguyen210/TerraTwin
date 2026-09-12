"""A6 — sổ đăng ký mô hình: đăng ký, đổi bản đang chạy, quay lui, chỉ 1 active."""
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.services import model_registry as reg


def test_register_activate_and_rollback():
    db = SessionLocal()
    try:
        kind = "unit_test_kind"
        v1 = reg.register(db, kind, "v1", data_hash="aaa", activate=True)
        assert reg.active_for(db, kind).id == v1.id
        v2 = reg.register(db, kind, "v2", data_hash="bbb", activate=True)
        # Đổi bản đang chạy sang v2; v1 không còn active (chỉ 1 active/kind).
        assert reg.active_for(db, kind).id == v2.id
        # QUAY LUI về v1 bằng một lời gọi.
        reg.activate(db, v1.id)
        assert reg.active_for(db, kind).id == v1.id
        actives = [m for m in reg.list_versions(db, kind) if m.active]
        assert len(actives) == 1 and actives[0].id == v1.id
    finally:
        db.close()


def test_data_hash_recorded():
    db = SessionLocal()
    try:
        mv = reg.register(db, "hash_kind", "v1", data_hash="deadbeef",
                          metrics={"csi_pct": 61.0})
        d = reg.to_dict(mv)
        assert d["data_hash"] == "deadbeef"
        assert d["metrics"]["csi_pct"] == 61.0
        assert d["active"] is False
    finally:
        db.close()


def test_endpoints_auth_and_switch():
    with TestClient(app) as c:
        # GET công khai.
        assert c.get("/api/models").status_code == 200
        # POST + activate cần đăng nhập.
        assert c.post("/api/models", json={"kind": "k", "version": "v"}).status_code == 401
        assert c.post("/api/models/1/activate").status_code == 401

        c.post("/api/auth/register",
               json={"email": "reg@x.com", "password": "Passw0rd1", "name": "R"})
        tok = c.post("/api/auth/login",
                     json={"email": "reg@x.com", "password": "Passw0rd1"}).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        a = c.post("/api/models", json={"kind": "api_kind", "version": "1.0", "activate": True}, headers=H).json()
        b = c.post("/api/models", json={"kind": "api_kind", "version": "2.0", "activate": True}, headers=H).json()
        # Đổi qua lại bằng một lời gọi API.
        r = c.post(f"/api/models/{a['id']}/activate", headers=H)
        assert r.status_code == 200 and r.json()["active"] is True
        models = c.get("/api/models?kind=api_kind").json()["models"]
        actives = [m for m in models if m["active"]]
        assert len(actives) == 1 and actives[0]["id"] == a["id"]
