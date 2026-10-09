"""CỔNG GĐ6 kế hoạch tổng — canh đất mỗi ngày:

  · nhật ký thửa chỉ bật "có thay đổi" khi có thay đổi THẬT (mưa nhỏ, cảnh radar không nước, số đo bình
    thường = bối cảnh, không phải sự kiện); "từ lần mở trước" đúng nghĩa (đánh dấu đã xem → lần sau im);
  · số đo cảm biến (đã ký) hiện trên nhật ký ngay ở lượt gọi nhanh kế tiếp — giao diện gọi mỗi 5 giây;
  · cảm biến mặn vượt ngưỡng nhắc → sự kiện thật;
  · đối chiếu ba chiều: câu trả lời ↔ radar cùng tuần ↔ mưa 3 ngày → khớp / lệch / chưa đủ;
  · so sánh 4 thửa trên một màn, đánh dấu giá trị thuận lợi nhất theo RIÊNG từng tiêu chí.
Không chạm mạng (nguồn ngoài giả lập).
"""
from __future__ import annotations

import base64
import json
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"
LAT, LON = 16.5751, 107.4952


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import plot_journal, quota
    engine = create_engine(f"sqlite:///{tmp_path/'j.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    quota.reset()
    today = date.today()
    quiet = {"rain": [{"date": (today - timedelta(days=i)).isoformat(), "precip": 3.0} for i in range(10)],
             "radar": {"has_baseline": True, "scenes": [
                 {"date": (today - timedelta(days=2)).isoformat(), "p50": -9.1, "water": None, "judged": True}]}}
    monkeypatch.setattr(plot_journal, "_external", lambda lat, lon, since: quiet)
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


def _plot(c, h, lat=LAT, lon=LON):
    r = c.post("/api/plots", headers=h, json={"name": "Ruộng Quảng Điền", "location": {"lat": lat, "lon": lon}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class Dev:
    def __init__(self):
        self.k = Ed25519PrivateKey.generate()
        raw = self.k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.pub = base64.b64encode(raw).decode()
        self.id = None

    def sign(self, seq, metrics):
        payload = json.dumps({"device_id": self.id, "seq": seq, "ts": datetime.now(timezone.utc).isoformat(),
                              "metrics": metrics})
        return {"payload": payload, "sig": base64.b64encode(self.k.sign(payload.encode())).decode()}


def test_khong_co_thay_doi_that_thi_im(c):
    h = _login(c, "j1@vd.vn")
    pid = _plot(c, h)
    j = c.get(f"/api/plots/{pid}/journal", headers=h).json()
    assert j["changed"] is False and j["n_significant"] == 0 and j["first_open"] is True
    kinds = {e["kind"] for e in j["events"]}
    assert kinds <= {"radar"}                                           # cảnh không nước = bối cảnh
    assert "không có thay đổi đáng kể" in j["summary"] and "không thấy nước" in j["summary"]


def test_mua_rat_to_va_radar_thay_nuoc_la_thay_doi_that(c, monkeypatch):
    from app.services import plot_journal
    today = date.today()
    wet = {"rain": [{"date": (today - timedelta(days=1)).isoformat(), "precip": 87.0},
                    {"date": today.isoformat(), "precip": 20.0}],
           "radar": {"has_baseline": True, "scenes": [
               {"date": today.isoformat(), "p50": -21.0, "water": "≥50%", "judged": True}]}}
    monkeypatch.setattr(plot_journal, "_external", lambda lat, lon, since: wet)
    h = _login(c, "j2@vd.vn")
    pid = _plot(c, h)
    j = c.get(f"/api/plots/{pid}/journal", headers=h).json()
    sig = [e for e in j["events"] if e["significant"]]
    assert {e["kind"] for e in sig} == {"rain", "water"}
    assert any(e["kind"] == "rain" and not e["significant"] for e in j["events"])   # 20 mm: bối cảnh
    assert j["changed"] is True and "107 mm" in j["summary"] and "thấy nước phủ ≥50%" in j["summary"]


def test_tu_lan_mo_truoc_danh_dau_da_xem_thi_lan_sau_khong_ke_lai(c, monkeypatch):
    from app import routes_learn
    monkeypatch.setattr(routes_learn, "_model_index_on", lambda *a: None)
    h = _login(c, "j3@vd.vn")
    pid = _plot(c, h)
    r = c.post("/api/observations", headers=h, json={"location": {"lat": LAT, "lon": LON}, "module_id": "flood",
                                                     "observed_on": date.today().isoformat(), "outcome": "occurred"})
    assert r.status_code == 201, r.text
    j = c.get(f"/api/plots/{pid}/journal", headers=h).json()
    assert j["changed"] is True
    rec = next(e for e in j["events"] if e["kind"] == "answer")["reconcile"]
    # người dùng nói ngập; radar cùng tuần không thấy nước, mưa 3 ngày 12 mm → lệch, nói rõ chỗ lệch
    assert rec["verdict"] == "mismatch" and rec["radar_water"] is False and rec["rain_3d_mm"] == 12.0
    time.sleep(1.1)
    assert c.post(f"/api/plots/{pid}/journal/seen", headers=h).status_code == 200
    j2 = c.get(f"/api/plots/{pid}/journal", headers=h).json()
    assert j2["first_open"] is False and not any(e["kind"] == "answer" for e in j2["events"])


def test_so_do_cam_bien_hien_ngay_tren_nhat_ky_va_man_vuot_nguong(c):
    h = _login(c, "j4@vd.vn")
    pid = _plot(c, h)
    d = Dev()
    r = c.post("/api/iot/devices", headers=h, json={"name": "Đầu đo EC", "public_key": d.pub,
                                                    "lat": LAT + 0.001, "lon": LON})
    assert r.status_code == 200, r.text
    d.id = r.json()["id"]
    t0 = time.monotonic()
    assert c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [
        d.sign(1, {"ec_ms_cm": 1.2, "salinity_ppt": 0.7})]}).json()["accepted"] == 1
    j = c.get(f"/api/plots/{pid}/journal?fast=1", headers=h).json()
    assert time.monotonic() - t0 < 10
    s = next(e for e in j["events"] if e["kind"] == "sensor")
    assert s["metrics"]["salinity_ppt"] == 0.7 and s["significant"] is False and j["summary"] is None
    # nhúng đầu đo vào cốc nước muối
    assert c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [
        d.sign(2, {"ec_ms_cm": 52.0, "salinity_ppt": 34.6})]}).json()["accepted"] == 1
    j = c.get(f"/api/plots/{pid}/journal?fast=1", headers=h).json()
    s = next(e for e in j["events"] if e["kind"] == "sensor")
    assert s["significant"] is True and "34.6" in s["text"] and "≥ 4‰" in s["text"] and j["changed"] is True


def test_nhat_ky_chi_cua_chu_thua(c):
    h1, h2 = _login(c, "j5@vd.vn"), _login(c, "j6@vd.vn")
    pid = _plot(c, h1)
    assert c.get(f"/api/plots/{pid}/journal", headers=h2).status_code == 404
    assert c.get(f"/api/plots/{pid}/journal").status_code == 401


def test_doi_chieu_ba_chieu():
    from app.services import plot_journal as pj
    d = "2026-10-12"
    scenes = [{"date": "2026-10-10", "water": "≥50%", "judged": True}]
    rain = [{"date": "2026-10-10", "precip": 60.0}, {"date": "2026-10-11", "precip": 30.0}]
    assert pj.reconcile(d, True, rain, scenes)["verdict"] == "match"
    assert pj.reconcile(d, False, rain, scenes)["verdict"] == "mismatch"
    assert pj.reconcile(d, True, [{"date": "2026-10-11", "precip": 5.0}], scenes)["verdict"] == "partial"
    assert pj.reconcile(d, True, None, [])["verdict"] == "insufficient"


def test_so_sanh_bon_thua_tren_mot_man(c, monkeypatch):
    from app.services import plot_compare
    fake = {
        (10.03, 105.77): dict(water_events=4, elevation_m=1.2, lower_than_pct=88, slope_deg=0.1, river_km=0.3, coast_km=62.0,
                              salinity_zone="Đồng bằng sông Cửu Long", flood_10y=7, landslide_10y=0, drought_10y=2, land="Đất trồng trọt 90%"),
        (16.46, 107.59): dict(water_events=2, elevation_m=4.0, lower_than_pct=70, slope_deg=0.4, river_km=0.8, coast_km=11.0,
                              salinity_zone=None, flood_10y=6, landslide_10y=1, drought_10y=1, land="Xây dựng 70%"),
        (11.94, 108.44): dict(water_events=0, elevation_m=1490.0, lower_than_pct=40, slope_deg=6.2, river_km=2.1, coast_km=90.0,
                              salinity_zone=None, flood_10y=0, landslide_10y=5, drought_10y=0, land="Cây gỗ 60%"),
        (21.03, 105.85): dict(water_events=None, elevation_m=12.0, lower_than_pct=55, slope_deg=0.2, river_km=1.0, coast_km=95.0,
                              salinity_zone=None, flood_10y=3, landslide_10y=0, drought_10y=1, land="Xây dựng 95%"),
    }
    monkeypatch.setattr(plot_compare, "one", lambda lat, lon: {"lat": lat, "lon": lon, **fake[(lat, lon)]})
    pts = [{"lat": a, "lon": b, "name": n} for (a, b), n in zip(fake, ["Cần Thơ", "Huế", "Đà Lạt", "Hà Nội"])]
    r = c.post("/api/compare", json={"points": pts}).json()
    assert [x["name"] for x in r["columns"]] == ["Cần Thơ", "Huế", "Đà Lạt", "Hà Nội"]
    assert r["columns"][3]["water_read"] is False
    row = {x["key"]: x for x in r["rows"]}
    assert row["water_events"]["best"] == [2] and row["elevation_m"]["best"] == [2]
    assert row["landslide_10y"]["best"] == [0, 3] and row["salinity_zone"]["best"] is None
    assert row["salinity_zone"]["values"][1] == "ngoài vùng"
    assert "không phải lời khuyên" in r["note"]
    assert c.post("/api/compare", json={"points": pts[:1]}).status_code == 422
    assert c.post("/api/compare", json={"points": [pts[0], pts[0]]}).status_code == 422
    assert c.post("/api/compare", json={"points": pts + [{"lat": 12.0, "lon": 109.0}]}).status_code == 422


def test_ban_tin_sang_lay_tu_nhat_ky_chi_ke_thua_co_thay_doi(c):
    from app.db import SessionLocal, User
    from app.services import brief
    h = _login(c, "j7@vd.vn")
    _plot(c, h)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "j7@vd.vn").one()
        title, body = brief.compose(db, u)
        assert "Từ hôm qua" not in body                                  # không có gì đổi → không kể
    finally:
        db.close()
    d = Dev()
    d.id = c.post("/api/iot/devices", headers=h, json={"name": "EC", "public_key": d.pub, "lat": LAT, "lon": LON}).json()["id"]
    c.post("/api/iot/ingest", json={"device_id": d.id, "readings": [d.sign(1, {"salinity_ppt": 9.5})]})
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "j7@vd.vn").one()
        title, body = brief.compose(db, u)
        assert "Từ hôm qua: Ruộng Quảng Điền" in body and "9.5" in body
    finally:
        db.close()
