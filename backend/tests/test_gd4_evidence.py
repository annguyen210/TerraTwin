"""CỔNG GĐ4 kế hoạch tổng — hồ sơ bằng chứng:

  · sửa MỘT ký tự trên bản hồ sơ → kiểm chứng báo đỏ (cả máy chủ lẫn script độc lập ops/verify_dossier.py);
  · con số bịa trong lời LLM bị chặn (câu bị loại, giữ câu mẫu); câu mẫu tự nó chỉ dùng số trong bằng chứng;
  · bằng chứng bao hàm (inclusion proof) kiểm được bằng script độc lập, không import mã máy chủ;
  · trạng thái neo OpenTimestamps: đã neo / chờ / chưa tới lượt / gốc lệch (sổ bị viết lại) → đỏ.
Không chạm mạng.
"""
from __future__ import annotations

import importlib.util
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

FACTS = {
    "schema": "terratwin.dossier/1", "lang": "vi",
    "location": {"lat": 16.4637, "lon": 107.5909, "area_ha": 0.5},
    "land_use": {"source": "ESA WorldCover 2021 v200 (10 m)", "year": "2021", "item": "ESA_WorldCover_10m_2021_v200_N15E105",
                 "pixels": 144, "classes": [{"code": 40, "name": "Đất trồng trọt", "pct": 81.9, "group": "crop"},
                                            {"code": 50, "name": "Xây dựng", "pct": 18.1, "group": "built"}]},
    "terrain": {"elevation_m": 3.4, "neighbours_sampled": 24, "radius_km": 5, "lower_than_pct": 83,
                "around_min_m": 0.8, "around_max_m": 41.5, "slope_deg": 0.42, "meaning": "…"},
    "history_10y": {"flood": {"name": "Lũ lụt", "events": 6, "peak_month": 10, "latest": "2025-10-28",
                              "worst_value": 312.4, "worst_date": "2020-10-18", "national_threshold": 95.23},
                    "drought": {"name": "Hạn hán", "events": 0, "peak_month": None, "latest": None,
                                "worst_value": 40.1, "worst_date": "2019-06-02", "national_threshold": 64.48}},
    "water_history_radar": {"n_scenes": 287, "first": "2017-01-04", "last": "2026-09-30", "track": 18,
                            "n_events": 2, "events": [
                                {"start": "2020-10-11", "end": "2020-10-23", "peak_cover": "64%", "n_scenes": 3, "min_p50_db": -21.7},
                                {"start": "2025-10-29", "end": "2025-10-29", "peak_cover": "38%", "n_scenes": 1, "min_p50_db": -19.2}],
                            "rule": {}, "method": "…", "limits": "…"},
    "missing": [],
}


def _ops(name: str):
    path = os.path.join(os.path.dirname(__file__), "..", "..", "ops", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _vi():
    from app.services import reqlang
    reqlang.set_lang("vi")


# ------------------------------------------------------------------ lời diễn giải có bằng chứng

def test_moi_cau_mau_deu_dan_bang_chung_co_that_va_chi_dung_so_trong_bang_chung():
    from app.services import guard, narrative
    n = narrative.build(FACTS)
    assert n["mode"] == "template" and n["blocked_sentences"] == 0
    assert len(n["sentences"]) >= 4
    for s in n["sentences"]:
        assert s["evidence"], s
        assert all(i in n["evidence"] for i in s["evidence"]), s
        allowed = guard.numbers_in(narrative._evidence_text(n["evidence"], s["evidence"]))
        assert guard.strip_invented_numbers(s["text"], allowed)[1] == [], s["text"]
    water = next(s for s in n["sentences"] if "water.summary" in s["evidence"])
    assert "2 đợt" in water["text"] and "287 cảnh" in water["text"] and "2025-10-29" in water["text"]
    ev = n["evidence"]["terrain.elevation"]
    assert ev["value"] == "3.4 m" and "latitude=16.4637" in ev["url"] and ev["source"].startswith("Copernicus DEM")
    assert {"source", "measured", "reproduce"} <= set(n["evidence"]["history.flood"])


def test_tieng_anh_va_ho_so_eudr_khong_dung_mau_dat():
    from app.services import narrative
    en = narrative.build(FACTS, lang="en")
    assert any("Sentinel-1 radar saw water" in s["text"] for s in en["sentences"])
    assert narrative.build({**FACTS, "kind": "eudr_plot"}) is None


def test_so_bia_trong_loi_llm_bi_chan_ca_cau(monkeypatch):
    from app.services import llm, narrative
    drafts = narrative.template_sentences(FACTS, narrative.catalog(FACTS))
    rewritten = [d["text"].replace("Radar Sentinel-1", "Ảnh radar") for d in drafts]
    i_terr = next(i for i, d in enumerate(drafts) if "terrain.elevation" in d["evidence"])
    rewritten[i_terr] = "Thửa cao 12.5 m, khá an toàn trước lũ."          # 12.5 không có trong bằng chứng
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Đây:\n" + json.dumps(rewritten, ensure_ascii=False))
    n = narrative.build(FACTS)                                             # không có mã hồ sơ → không cache
    assert n["mode"] == "llm" and n["blocked_sentences"] == 1
    assert n["sentences"][i_terr]["text"] == drafts[i_terr]["text"]        # giữ câu mẫu
    assert "12.5" not in json.dumps(n, ensure_ascii=False)
    assert n["sentences"][0].get("by") == "llm" and n["sentences"][0]["text"].startswith("Ảnh radar")


def test_llm_tra_sai_dinh_dang_thi_dung_cau_mau(monkeypatch):
    from app.services import llm, narrative
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: '["chỉ một câu"]')
    n = narrative.build(FACTS)
    assert n["mode"] == "template" and all("by" not in s for s in n["sentences"])


# ------------------------------------------------------------------ hồ sơ thật qua API

@pytest.fixture
def env(tmp_path, monkeypatch):
    from app import db as dbmod
    from app import routes_dossier
    from app.services import dossier

    engine = create_engine(f"sqlite:///{tmp_path/'d.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.delenv("TERRATWIN_SIGNING_KEY", raising=False)
    monkeypatch.setattr(routes_dossier.region, "classify", lambda lat, lon: {"kind": "land", "serviceable": True})
    monkeypatch.setattr(dossier, "build_facts", lambda lat, lon, area, db: {**FACTS, "location": {
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
        yield c
    app.dependency_overrides.clear()


def _issue(c, k=0):
    r = c.post("/api/dossier", json={"lat": 16.46 + k / 1000, "lon": 107.59, "area_ha": 0.5})
    assert r.status_code == 200, r.text
    return r.json()


def _doc(d):
    return {k: d[k] for k in ("id", "seq", "issued_at", "facts", "facts_canonical", "proof")}


def test_trang_ho_so_tra_loi_dien_giai_va_bang_chung(env):
    d = _issue(env)
    n = d["narrative"]
    assert n["sentences"] and n["evidence"]["water.summary"]["source"].startswith("Sentinel-1")
    assert d["anchor"] is None                                             # neo tắt trong test (conftest)


def test_sua_mot_ky_tu_ban_in_thi_kiem_chung_bao_do(env):
    c = env
    d = _issue(env)
    keys = {k["key_id"]: k["public_key_b64"] for k in c.get("/api/dossiers/keys").json()["keys"]}
    vd = _ops("verify_dossier")

    good = _doc(d)
    rep = vd.Report(); vd.check_document(good, keys, rep)
    assert rep.fail == 0
    assert c.post("/api/dossier/verify", json=good).json()["valid"] is True

    # Sửa đúng MỘT ký tự trong phần hiển thị (3.4 m → 3.9 m)
    bad = json.loads(json.dumps(good))
    bad["facts"]["terrain"]["elevation_m"] = 3.9
    assert c.post("/api/dossier/verify", json=bad).json()["valid"] is False
    rep = vd.Report(); vd.check_document(bad, keys, rep)
    assert rep.fail >= 1

    # Sửa MỘT ký tự trong chuỗi đã ký (và cả phần hiển thị cho khớp) — mã băm lệch
    canon = good["facts_canonical"]
    i = canon.index("Đất trồng trọt")
    bad2 = {**good, "facts_canonical": canon[:i] + "Đ" + "ấ" + "t trồng trọT" + canon[i + len("Đất trồng trọt"):]}
    bad2["facts"] = json.loads(bad2["facts_canonical"])
    rep = vd.Report(); vd.check_document(bad2, keys, rep)
    assert rep.fail >= 1
    assert c.post("/api/dossier/verify", json=bad2).json()["valid"] is False

    # Thời điểm phát hành bị lùi một chữ số → mục sổ lệch
    bad3 = {**good, "issued_at": good["issued_at"].replace(good["issued_at"][3], str((int(good["issued_at"][3]) + 1) % 10), 1)}
    rep = vd.Report(); vd.check_document(bad3, keys, rep)
    assert rep.fail >= 1


def test_inclusion_proof_kiem_duoc_bang_script_doc_lap(env, monkeypatch):
    c = env
    docs = [_issue(env, k) for k in range(7)]
    vd = _ops("verify_dossier")
    head = c.get("/api/log/sth").json()
    assert head["tree_size"] == 7
    for d in docs:
        inc = c.get(f"/api/log/inclusion?seq={d['seq']}&tree_size=7").json()
        proof = [bytes.fromhex(x) for x in inc["proof"]]
        leaf = vd.leaf_of(d["proof"]["entry_hash"])
        assert vd.verify_inclusion(leaf, d["seq"] - 1, 7, proof, bytes.fromhex(head["root_hash"]))
        other = vd.leaf_of(docs[(d["seq"]) % 7]["proof"]["entry_hash"])
        assert not vd.verify_inclusion(other, d["seq"] - 1, 7, proof, bytes.fromhex(head["root_hash"]))

    # Chạy nguyên luồng script (check_log) với mạng được thay bằng TestClient
    monkeypatch.setattr(vd, "get", lambda url, raw=False, timeout=60: c.get(url.replace("http://api", "")).json())
    keys = {k["key_id"]: k["public_key_b64"] for k in c.get("/api/dossiers/keys").json()["keys"]}
    rep = vd.Report(); vd.check_log("http://api", _doc(docs[3]), keys, rep)
    assert rep.fail == 0
    forged = _doc(docs[3]); forged["proof"] = {**forged["proof"], "entry_hash": docs[4]["proof"]["entry_hash"]}
    forged["seq"] = docs[3]["seq"]
    rep = vd.Report(); vd.check_log("http://api", forged, keys, rep)
    assert rep.fail >= 1


def test_trang_thai_neo_opentimestamps(env, monkeypatch):
    from app.db import SessionLocal
    from app.services import anchor, merkle, translog
    for k in range(3):
        _issue(env, k)
    db = SessionLocal()
    try:
        root2 = merkle.root(translog.leaves(db, 2)).hex()
        monkeypatch.setenv("TERRATWIN_ANCHORS_URL", "https://example.invalid/anchors.json")
        monkeypatch.setattr(anchor, "load", lambda force=False: [
            {"tree_size": 1, "root_hash": merkle.root(translog.leaves(db, 1)).hex(), "status": "pending",
             "file": "sth/1.txt", "ots": "sth/1.txt.ots", "submitted_at": "2026-10-09T23:17:40Z"},
            {"tree_size": 2, "root_hash": root2, "status": "confirmed", "bitcoin_height": 917001,
             "bitcoin_time": "2026-10-10T02:11:09Z", "file": "sth/2.txt", "ots": "sth/2.txt.ots"}])
        a1 = anchor.for_seq(db, 1)
        assert a1["status"] == "confirmed" and a1["tree_size"] == 2 and a1["bitcoin_height"] == 917001
        assert a1["ots_url"].endswith("/sth/2.txt.ots")
        vd = _ops("verify_dossier")
        assert vd.verify_inclusion(bytes.fromhex(a1["leaf_hash"]), 0, 2, [bytes.fromhex(x) for x in a1["proof"]],
                                   bytes.fromhex(root2))
        assert anchor.for_seq(db, 3)["status"] == "not_yet"
        monkeypatch.setattr(anchor, "load", lambda force=False: [
            {"tree_size": 2, "root_hash": "00" * 32, "status": "confirmed", "file": "sth/2.txt", "ots": "sth/2.txt.ots"}])
        assert anchor.for_seq(db, 1)["status"] == "root_mismatch"      # sổ đã bị viết lại sau khi neo → đỏ
        monkeypatch.setattr(anchor, "load", lambda force=False: None)
        assert anchor.for_seq(db, 1)["status"] == "unavailable"
    finally:
        db.close()
