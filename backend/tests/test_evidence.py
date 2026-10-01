"""Ảnh thực địa đã kiểm + gắn vào Hồ sơ đất số.

Ảnh thử được DỰNG bằng Pillow, có EXIF GPS/thời điểm/phần mềm như ảnh điện
thoại thật. Không chạm mạng.
"""
from __future__ import annotations

import base64
import io
import random
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import evidence, reqlang

PLOT = (16.4600, 107.5900)
NOW = datetime(2026, 10, 1, 9, 0, 0)


def _dms(v: float):
    v = abs(v)
    d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 2)
    return (float(d), float(m), float(s))


def photo(lat=None, lon=None, taken: datetime | None = None, software: str | None = None,
          seed: int = 1, size=(800, 600), fmt="JPEG") -> bytes:
    """Ảnh có kết cấu (nhiễu theo seed) — ảnh một màu thì mọi dHash như nhau."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (40, 30))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(1200)])
    img = img.resize(size, Image.Resampling.BICUBIC)
    ex = Image.Exif()
    if taken:
        ex.get_ifd(0x8769)[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
    if software:
        ex[0x0131] = software
    if lat is not None:
        g = ex.get_ifd(0x8825)
        g[1] = "N" if lat >= 0 else "S"; g[2] = _dms(lat)
        g[3] = "E" if lon >= 0 else "W"; g[4] = _dms(lon)
    buf = io.BytesIO()
    img.save(buf, fmt, exif=ex) if fmt == "JPEG" else img.save(buf, fmt)
    return buf.getvalue()


def _offset(lat, lon, north_m=0.0, east_m=0.0):
    import math
    return lat + north_m / 111_320, lon + east_m / (111_320 * math.cos(math.radians(lat)))


@pytest.fixture
def db(tmp_path):
    from app import db as dbmod
    engine = create_engine(f"sqlite:///{tmp_path/'e.db'}")
    dbmod.Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    reqlang.set_lang("vi")
    yield s
    s.close()


def _checks(res):
    return {c["id"]: c["ok"] for c in res["checks"]}


def test_anh_dung_cho_dung_luc_khop(db):
    lat, lon = _offset(*PLOT, north_m=30)
    r = evidence.analyze(db, photo(lat, lon, NOW - timedelta(days=3)), *PLOT, now=NOW)
    assert r["verdict"] == "match" and all(_checks(r).values())
    assert 25 < r["distance_m"] < 35


def test_anh_chup_cho_khac_khong_khop(db):
    lat, lon = _offset(*PLOT, north_m=5000)
    r = evidence.analyze(db, photo(lat, lon, NOW - timedelta(days=3)), *PLOT, now=NOW)
    assert r["verdict"] == "mismatch" and _checks(r)["location"] is False


def test_ban_kinh_theo_dien_tich_thua(db):
    lat, lon = _offset(*PLOT, east_m=250)
    small = evidence.analyze(db, photo(lat, lon, NOW), *PLOT, area_ha=0.1, now=NOW)
    big = evidence.analyze(db, photo(lat, lon, NOW), *PLOT, area_ha=20, now=NOW)
    assert _checks(small)["location"] is False and _checks(big)["location"] is True


def test_khong_gps_can_xem_them(db):
    r = evidence.analyze(db, photo(taken=NOW), *PLOT, now=NOW)
    assert r["verdict"] == "review" and _checks(r)["gps"] is False
    assert _checks(r)["location"] is None


def test_anh_cu_can_xem_them_anh_tuong_lai_khong_khop(db):
    lat, lon = _offset(*PLOT, north_m=10)
    old = evidence.analyze(db, photo(lat, lon, NOW - timedelta(days=200)), *PLOT, now=NOW)
    assert old["verdict"] == "review" and _checks(old)["time"] is None
    fut = evidence.analyze(db, photo(lat, lon, NOW + timedelta(days=30)), *PLOT, now=NOW)
    assert fut["verdict"] == "mismatch" and _checks(fut)["time"] is False


def test_dau_phan_mem_chinh_anh(db):
    lat, lon = _offset(*PLOT, north_m=10)
    r = evidence.analyze(db, photo(lat, lon, NOW, software="Adobe Photoshop 25.0"), *PLOT, now=NOW)
    assert r["verdict"] == "review" and _checks(r)["edited"] is False


def test_anh_dung_lai_cho_thua_khac_bi_bat_ke_ca_khi_nen_lai(db):
    lat, lon = _offset(*PLOT, north_m=10)
    raw = photo(lat, lon, NOW, seed=7)
    evidence.store(db, evidence.analyze(db, raw, *PLOT, now=NOW), *PLOT)
    other = (10.24, 106.37)                               # Bến Tre, cách ~700 km
    same = evidence.analyze(db, raw, *other, now=NOW)
    assert _checks(same)["duplicate"] is False and same["verdict"] == "mismatch"
    # Nén lại + thu nhỏ: khác từng byte nhưng vẫn là một cảnh.
    im = Image.open(io.BytesIO(raw)).resize((400, 300))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=55)
    near = evidence.analyze(db, buf.getvalue(), *other, now=NOW)
    assert _checks(near)["duplicate"] is False
    # Ảnh KHÁC hẳn thì không bị nghi.
    assert _checks(evidence.analyze(db, photo(seed=99), *other, now=NOW))["duplicate"] is True


def test_nop_lai_cho_chinh_thua_do_khong_phai_dung_lai(db):
    lat, lon = _offset(*PLOT, north_m=10)
    raw = photo(lat, lon, NOW, seed=3)
    evidence.store(db, evidence.analyze(db, raw, *PLOT, now=NOW), *PLOT)
    assert _checks(evidence.analyze(db, raw, *PLOT, now=NOW))["duplicate"] is True


def test_anh_mot_mau_khong_bi_ket_toi_oan(db):
    def flat(color):
        buf = io.BytesIO(); Image.new("RGB", (640, 480), color).save(buf, "JPEG"); return buf.getvalue()
    evidence.store(db, evidence.analyze(db, flat((0, 0, 0)), *PLOT, now=NOW), *PLOT)
    r = evidence.analyze(db, flat((5, 5, 5)), 10.24, 106.37, now=NOW)
    assert _checks(r)["duplicate"] is True


def test_anh_thu_nho_da_xoa_exif(db):
    lat, lon = _offset(*PLOT, north_m=10)
    r = evidence.analyze(db, photo(lat, lon, NOW, software="Snapseed", size=(2000, 1500)), *PLOT, now=NOW)
    t = Image.open(io.BytesIO(r["thumb"]))
    assert max(t.size) <= evidence.THUMB_PX
    ex = t.getexif()
    assert not ex.get_ifd(0x8825) and 0x0131 not in ex, "ảnh thu nhỏ không được mang GPS/thiết bị"


def test_anh_hong_hoac_qua_lon(db):
    with pytest.raises(evidence.PhotoError):
        evidence.analyze(db, b"khong phai anh" * 10, *PLOT, now=NOW)
    with pytest.raises(evidence.PhotoError):
        evidence.analyze(db, b"\xff" * (evidence.MAX_BYTES + 1), *PLOT, now=NOW)


# ---------------------------------------------------------------- API + hồ sơ

@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import db as dbmod
    from app import routes_dossier
    from app.services import dossier

    engine = create_engine(f"sqlite:///{tmp_path/'a.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.delenv("TERRATWIN_SIGNING_KEY", raising=False)
    monkeypatch.setattr(routes_dossier.region, "classify", lambda lat, lon: {"serviceable": True})
    monkeypatch.setattr(dossier, "build_facts", lambda lat, lon, area, db: {
        "schema": "terratwin.dossier/1", "location": {"lat": lat, "lon": lon, "area_ha": area}})
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        yield c, Session
    app.dependency_overrides.clear()


def _upload(c, raw, lat=PLOT[0], lon=PLOT[1]):
    return c.post("/api/evidence", json={"lat": lat, "lon": lon, "name": "a.jpg",
                                         "data_b64": base64.b64encode(raw).decode()})


def test_api_kiem_anh_khong_tra_toa_do_gps(client):
    c, _ = client
    lat, lon = _offset(*PLOT, north_m=20)
    r = _upload(c, photo(lat, lon, datetime.now() - timedelta(days=1)))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verdict"] == "match" and len(d["id"]) == 12
    assert "gps_lat" not in d and "gps_lon" not in d
    t = c.get(d["thumb_url"])
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg"


def test_api_anh_hong_tra_422(client):
    c, _ = client
    assert _upload(c, b"xin chao, day khong phai anh").status_code == 422


def test_ho_so_kem_anh_dong_bang_va_bat_anh_bi_thay(client):
    c, Session = client
    lat, lon = _offset(*PLOT, north_m=20)
    pid = _upload(c, photo(lat, lon, datetime.now())).json()["id"]
    d = c.post("/api/dossier", json={"lat": PLOT[0], "lon": PLOT[1], "evidence_ids": [pid]}).json()
    assert d["facts"]["field_evidence"][0]["id"] == pid
    checks = {x["id"]: x["ok"] for x in d["verification"]["checks"]}
    assert checks["evidence"] is True and d["verification"]["valid"] is True

    from app.db import FieldPhoto
    with Session() as s:                                   # thay ảnh trong CSDL
        s.get(FieldPhoto, pid).thumb = photo(seed=42)
        s.commit()
    v = c.get(f"/api/dossier/{d['id']}").json()["verification"]
    assert v["valid"] is False
    assert {x["id"]: x["ok"] for x in v["checks"]}["evidence"] is False


def test_khong_gan_anh_cua_thua_khac(client):
    c, _ = client
    pid = _upload(c, photo(seed=5), lat=10.24, lon=106.37).json()["id"]
    r = c.post("/api/dossier", json={"lat": PLOT[0], "lon": PLOT[1], "evidence_ids": [pid]})
    assert r.status_code == 422
