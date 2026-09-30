"""Hồ sơ đất số: phát hành, kiểm chứng, và MỌI kiểu gian lận phải bị bắt.

Không chạm mạng: build_facts và region.classify được giả lập. Kiểm trên CSDL
thật của test (SQLite tạm; CI chạy thêm trên PostgreSQL).
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

FACTS = {"schema": "terratwin.dossier/1", "lang": "vi",
         "location": {"lat": 16.46, "lon": 107.59, "area_ha": 0.5},
         "land_use": {"dominant_group": "built", "dominant_pct": 100.0},
         "current_risk": {"terrascore": {"score": 88, "grade": "A"}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app import db as dbmod
    from app import routes_dossier
    from app.services import dossier

    engine = create_engine(f"sqlite:///{tmp_path/'d.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.delenv("TERRATWIN_SIGNING_KEY", raising=False)
    monkeypatch.setattr(routes_dossier.region, "classify",
                        lambda lat, lon: {"kind": "land", "serviceable": True})
    monkeypatch.setattr(dossier, "build_facts",
                        lambda lat, lon, area, db: {**FACTS, "location": {
                            "lat": lat, "lon": lon, "area_ha": area}})

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


def _issue(c, lat=16.46, lon=107.59):
    r = c.post("/api/dossier", json={"lat": lat, "lon": lon, "area_ha": 0.5})
    assert r.status_code == 200, r.text
    return r.json()


def test_phat_hanh_hop_le_du_bon_phep_kiem(env):
    c, _ = env
    d = _issue(c)
    assert d["verification"]["valid"] is True
    assert {x["id"] for x in d["verification"]["checks"]} == {"content", "entry", "signature", "chain"}
    assert d["seq"] == 1 and d["proof"]["prev_hash"] == "0" * 64
    assert d["url"].endswith("/h/" + d["id"]) and len(d["id"]) == 12
    assert d["qr"].startswith("data:image/svg+xml")
    assert c.get(f"/api/dossier/{d['id']}").json()["verification"]["valid"] is True


def test_sua_noi_dung_trong_so_bi_bat(env):
    c, Session = env
    d = _issue(c)
    from app.db import Dossier
    with Session() as s:
        row = s.get(Dossier, d["id"])
        f = json.loads(row.facts_json)
        f["land_use"]["dominant_group"] = "crop"          # "đất xây dựng" → "đất ruộng"
        row.facts_json = json.dumps(f, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        s.commit()
    v = c.get(f"/api/dossier/{d['id']}").json()["verification"]
    assert v["valid"] is False
    assert [x["ok"] for x in v["checks"] if x["id"] == "content"] == [False]


def test_sua_roi_tu_bam_lai_cho_khop_van_bi_bat_nho_chu_ky(env):
    """Kẻ gian có quyền ghi CSDL: sửa nội dung, tính lại facts_hash VÀ entry_hash
    cho khớp hết. Mã băm đều đúng — chỉ chữ ký Ed25519 là không giả được."""
    c, Session = env
    d = _issue(c)
    from app.db import Dossier
    from app.services import dossier as svc
    with Session() as s:
        row = s.get(Dossier, d["id"])
        f = json.loads(row.facts_json)
        f["current_risk"]["terrascore"]["score"] = 100
        row.facts_json = svc.canonical(f)
        row.facts_hash = svc.sha256_hex(row.facts_json)
        row.entry_hash = svc.sha256_hex(svc.entry_message(
            row.seq, row.id, svc._iso(row.created_at), row.facts_hash, row.prev_hash))
        s.commit()
    checks = {x["id"]: x["ok"] for x in
              c.get(f"/api/dossier/{d['id']}").json()["verification"]["checks"]}
    assert checks == {"content": True, "entry": True, "signature": False, "chain": True}


def test_xoa_mot_ho_so_cu_lam_gay_moc_xich(env):
    c, Session = env
    ids = [_issue(c, 16.46 + i / 100)["id"] for i in range(3)]
    from app.db import Dossier
    with Session() as s:
        s.delete(s.get(Dossier, ids[1]))
        s.commit()
    checks = {x["id"]: x["ok"] for x in
              c.get(f"/api/dossier/{ids[2]}").json()["verification"]["checks"]}
    assert checks["chain"] is False and checks["signature"] is True


def test_kiem_tep_da_tai_ve(env):
    c, _ = env
    d = _issue(c)
    doc = {k: d[k] for k in ("id", "seq", "issued_at", "facts", "proof")}
    ok = c.post("/api/dossier/verify", json=doc).json()
    assert ok["valid"] is True and ok["matches_registry"] is True
    doc["facts"]["location"]["area_ha"] = 5.0             # sửa diện tích trên bản in
    bad = c.post("/api/dossier/verify", json=doc).json()
    assert bad["valid"] is False and bad["matches_registry"] is False
    assert c.post("/api/dossier/verify", json={"id": "khongco"}).json()["found"] is False


def test_so_cong_khai_khong_lo_ma_hay_toa_do_va_moc_lien_mach(env):
    c, _ = env
    for i in range(3):
        _issue(c, 10.0 + i)
    log = c.get("/api/dossiers/log").json()
    assert log["total"] == 3
    text = json.dumps(log)
    assert '"id"' not in text and "lat" not in text and "facts\"" not in text
    e = log["entries"]                                    # mới nhất trước
    assert [x["seq"] for x in e] == [3, 2, 1]
    assert e[0]["prev_hash"] == e[1]["entry_hash"] and e[1]["prev_hash"] == e[2]["entry_hash"]


def test_ben_thu_ba_tu_kiem_chu_ky_chi_voi_du_lieu_cong_khai(env):
    """Không cần tin máy chủ lúc kiểm: khoá công khai + sổ công khai là đủ."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    c, _ = env
    _issue(c)
    keys = c.get("/api/dossiers/keys").json()["keys"]
    assert keys and all("private" not in json.dumps(k).lower() for k in keys)
    pub = {k["key_id"]: k["public_key_b64"] for k in keys}
    for e in c.get("/api/dossiers/log").json()["entries"]:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub[e["key_id"]])).verify(
            base64.b64decode(e["signature"]), e["entry_hash"].encode("ascii"))


def test_khoa_tu_sinh_duoc_giu_qua_cac_lan_phat_hanh(env):
    c, _ = env
    assert _issue(c)["proof"]["key_id"] == _issue(c, 11.0)["proof"]["key_id"]


def test_khoa_tu_bien_moi_truong(env, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.services import signing
    k = Ed25519PrivateKey.generate()
    seed = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    monkeypatch.setenv("TERRATWIN_SIGNING_KEY", base64.b64encode(seed).decode())
    c, _ = env
    d = _issue(c)
    raw = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert d["proof"]["key_id"] == signing.key_id_for(raw)
    assert d["verification"]["valid"] is True
    src = {x["key_id"]: x["source"] for x in c.get("/api/dossiers/keys").json()["keys"]}
    assert src[d["proof"]["key_id"]] == "env"


def test_ngoai_pham_vi_tu_choi(env, monkeypatch):
    c, _ = env
    from app import routes_dossier
    monkeypatch.setattr(routes_dossier.region, "classify",
                        lambda lat, lon: {"serviceable": False, "note": "Mặt nước"})
    assert c.post("/api/dossier", json={"lat": 16.0, "lon": 109.5}).status_code == 422


def test_ma_khong_ton_tai_404(env):
    c, _ = env
    assert c.get("/api/dossier/khongcoma123").status_code == 404
