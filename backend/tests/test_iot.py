"""IoT ký số: thiết bị là khoá Ed25519; mọi kiểu giả mạo/phát lại/số phi vật lý đều bị chặn."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import quota
    engine = create_engine(f"sqlite:///{tmp_path/'iot.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    quota.reset()
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as cl:
        yield cl
    app.dependency_overrides.clear()


def _login(c, email):
    tok = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "N"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


class Dev:
    def __init__(self):
        self.k = Ed25519PrivateKey.generate()
        raw = self.k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.pub = base64.b64encode(raw).decode()
        self.id = None

    def sign(self, seq, metrics, ts=None, device_id=None):
        ts = ts or datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"device_id": device_id or self.id, "seq": seq, "ts": ts, "metrics": metrics})
        return {"payload": payload, "sig": base64.b64encode(self.k.sign(payload.encode())).decode()}


def _register(c, h, dev, **kw):
    r = c.post("/api/iot/devices", headers=h, json={"name": "Trạm vườn 1", "public_key": dev.pub, **kw})
    assert r.status_code == 200, r.text
    dev.id = r.json()["id"]
    return r.json()


def test_nhan_so_do_da_ky_va_xuat_kiem_doc_lap(c):
    h = _login(c, "iot1@vd.vn")
    d = Dev()
    _register(c, h, d)
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [
        d.sign(1, {"soil_moisture_pct": 35.5, "air_temp_c": 27.0}),
        d.sign(2, {"soil_moisture_pct": 34.0, "rain_mm": 1.2})]})
    assert r.status_code == 200 and r.json()["accepted"] == 2
    ser = c.get(f"/api/iot/devices/{d.id}/readings", headers=h).json()["series"]
    assert [x["soil_moisture_pct"] for x in ser] == [35.5, 34.0]
    # Bản xuất kiểm được KHÔNG cần tin máy chủ: chữ ký đúng trên đúng chuỗi.
    ex = c.get(f"/api/iot/devices/{d.id}/export", headers=h).json()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(ex["public_key"]))
    for rec in ex["readings"]:
        pub.verify(base64.b64decode(rec["signature"]), rec["payload"].encode())


def test_chu_ky_sai_phat_lai_mao_danh_deu_bi_chan(c):
    h = _login(c, "iot2@vd.vn")
    d, other = Dev(), Dev()
    _register(c, h, d)
    _register(c, h, other)
    # chữ ký bằng khoá KHÁC
    forged = other.sign(1, {"soil_moisture_pct": 50}, device_id=d.id)
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [forged]})
    assert r.status_code == 401
    # sửa số đo sau khi ký
    ok = d.sign(1, {"soil_moisture_pct": 50})
    tampered = {"payload": ok["payload"].replace("50", "90"), "sig": ok["sig"]}
    assert c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [tampered]}).status_code == 401
    # gói đúng → nhận; gửi lại y nguyên → phát lại, bị chặn
    assert c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [ok]}).json()["accepted"] == 1
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [ok]})
    assert r.status_code == 422 and r.json()["detail"]["rejected"][0]["reason"] == "replay"
    # gói ký hợp lệ của thiết bị khác gửi dưới tên thiết bị này
    pkt = other.sign(5, {"soil_moisture_pct": 40})
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [pkt]})
    assert r.status_code == 401


def test_so_do_phi_vat_ly_tuong_lai_qua_cu_chi_so_la_bi_loai(c):
    h = _login(c, "iot3@vd.vn")
    d = Dev()
    _register(c, h, d)
    now = datetime.now(timezone.utc)
    bad = [d.sign(1, {"soil_moisture_pct": 140}),
           d.sign(2, {"air_temp_c": 25}, ts=(now + timedelta(hours=2)).isoformat()),
           d.sign(3, {"air_temp_c": 25}, ts=(now - timedelta(days=40)).isoformat()),
           d.sign(4, {"radiation_sv": 1.0})]
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": bad})
    reasons = [x["reason"] for x in r.json()["detail"]["rejected"]]
    assert r.status_code == 422 and reasons == ["implausible", "bad_time", "bad_time", "bad_metrics"]
    # gửi bù sau 5 ngày mất sóng: HỢP LỆ
    late = d.sign(5, {"soil_moisture_pct": 30}, ts=int((now - timedelta(days=5)).timestamp()))
    assert c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [late]}).json()["accepted"] == 1


def test_khong_xem_duoc_thiet_bi_nguoi_khac_va_thu_hoi_chan_gui(c):
    ha, hb = _login(c, "iot4@vd.vn"), _login(c, "iot5@vd.vn")
    d = Dev()
    _register(c, ha, d)
    assert c.get(f"/api/iot/devices/{d.id}/readings", headers=hb).status_code == 404
    assert c.get(f"/api/iot/devices/{d.id}/export", headers=hb).status_code == 404
    assert c.delete(f"/api/iot/devices/{d.id}", headers=hb).status_code == 404
    assert c.post("/api/iot/devices", headers=hb, json={"name": "x", "public_key": d.pub}).status_code == 409
    assert c.delete(f"/api/iot/devices/{d.id}", headers=ha).json()["revoked"]
    r = c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [d.sign(1, {"air_temp_c": 25})]})
    assert r.status_code == 404


def test_khoa_khong_hop_le_va_gan_ho_so_nguoi_khac_bi_tu_choi(c):
    h = _login(c, "iot6@vd.vn")
    assert c.post("/api/iot/devices", headers=h, json={"name": "x", "public_key": "A" * 44}).status_code == 422
    d = Dev()
    r = c.post("/api/iot/devices", headers=h, json={"name": "x", "public_key": d.pub, "dossier_id": "khongcoaicaxx"})
    assert r.status_code == 404


def test_hom_nay_nhac_dat_kho_va_thiet_bi_im_lang(c):
    h = _login(c, "iot7@vd.vn")
    dry, silent = Dev(), Dev()
    _register(c, h, dry, kind="simulator")
    _register(c, h, silent)
    c.post("/api/iot/ingest", json={"device_id": dry.id, "readings": [dry.sign(1, {"soil_moisture_pct": 12})]})
    items = [i for i in c.get("/api/today", headers=h).json()["items"] if i["kind"] == "device"]
    titles = " | ".join(i["title"] for i in items)
    assert "Đất khô" in titles and "(giả lập)" in titles and "im lặng" in titles


def test_xoa_tai_khoan_xoa_thiet_bi_va_so_do(c):
    h = _login(c, "iot8@vd.vn")
    d = Dev()
    _register(c, h, d)
    c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [d.sign(1, {"air_temp_c": 25})]})
    r = c.delete("/api/account", headers=h)
    assert r.status_code in (200, 204), r.text
    from app import db as dbmod
    from app.db import Device, SensorReading
    with dbmod.SessionLocal() as s:
        assert s.query(Device).count() == 0 and s.query(SensorReading).count() == 0
