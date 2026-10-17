"""Lược đồ JSON công khai của tệp hồ sơ (17/10/2026): hồ sơ phát hành thật phải khớp; tệp sai định dạng phải bị bắt.

Lược đồ chỉ kiểm ĐỊNH DẠNG — toàn vẹn (băm, chữ ký, móc xích) có test riêng ở test_dossier.py.
"""
from __future__ import annotations

import copy
import json
import os

import jsonschema
import pytest

HERE = os.path.dirname(__file__)
PATH = os.path.join(HERE, "..", "data", "schema", "terratwin-document-1.schema.json")


def _schema():
    return json.load(open(PATH, encoding="utf-8"))


def test_luoc_do_hop_le_va_id_tro_dung_tep_trong_kho():
    s = _schema()
    jsonschema.Draft202012Validator.check_schema(s)
    assert s["$id"].endswith("/main/backend/data/schema/terratwin-document-1.schema.json")
    assert s["$id"].startswith("https://raw.githubusercontent.com/annguyen210/TerraTwin/")


@pytest.fixture
def land_doc(monkeypatch):
    """Hồ sơ đất phát hành bằng build_facts THẬT (chỉ giả lập nguồn mạng) → tệp tải về."""
    from app.db import SessionLocal
    from app.services import dossier, landuse, passport
    monkeypatch.setattr(passport, "build", lambda lat, lon: {"available": True, "terrain": {"elevation_m": 2.0},
                                                             "history": {"flood": {"events": 2}}, "caveat": "c"})
    monkeypatch.setattr(landuse, "composition", lambda lat, lon: {"label": "Đất trồng trọt", "dominant_group": "crop"})
    monkeypatch.setattr(dossier, "_water_section", lambda lat, lon: {
        "events": [{"start": "2020-10-10", "end": "2020-10-10", "season": "in"}], "n_events": 1, "n_in": 1, "n_out": 0})
    with SessionLocal() as db:
        facts = dossier.build_facts(16.5751, 107.4952, 0.4, db)
        row = dossier.issue(db, facts, 16.5751, 107.4952)
        return dossier.document(row, db)


def test_ho_so_dat_phat_hanh_that_khop_luoc_do(land_doc, doc_schema):
    doc_schema(land_doc)
    doc_schema({**land_doc, "url": "https://x/h/abc", "verification": {"valid": True}})   # API trả thêm trường sống


@pytest.mark.parametrize("mutate, why", [
    (lambda d: d["facts"].__setitem__("predictions_included", True), "dự báo lọt vào nội dung ký"),
    (lambda d: d["proof"].__setitem__("algorithm", "RSA"), "thuật toán lạ"),
    (lambda d: d["proof"].__setitem__("signature", "abc"), "chữ ký không phải 64 byte base64"),
    (lambda d: d["proof"].__setitem__("facts_hash", "XYZ"), "băm không phải hex64"),
    (lambda d: d.__setitem__("id", "llllllllllll"), "mã có ký tự bị loại (l)"),
    (lambda d: d["facts"].__setitem__("schema", "terratwin.dossier/9"), "loại nội dung không có"),
    (lambda d: d["facts"].__setitem__("kind", "eudr_plot"), "hồ sơ đất mang nhãn EUDR"),
    (lambda d: d["facts"]["location"].__setitem__("lat", 123), "vĩ độ ngoài khoảng"),
    (lambda d: d["facts"]["evidence_classes"].__setitem__("terrain", "guessed"), "loại bằng chứng lạ"),
    (lambda d: d.pop("facts_canonical"), "thiếu chuỗi đã băm"),
])
def test_tep_sai_dinh_dang_bi_bat(land_doc, doc_schema, mutate, why):
    bad = copy.deepcopy(land_doc)
    mutate(bad)
    assert list(doc_schema.validator.iter_errors(bad)), why


def test_ho_so_cu_co_anh_chup_du_bao_van_khop(land_doc, doc_schema):
    """Hồ sơ phát hành trước 03/10/2026 còn current_risk/track_record, chưa có predictions_included — vẫn đúng định dạng."""
    old = copy.deepcopy(land_doc)
    for k in ("predictions_included", "predictions_note", "evidence_classes", "water_history_radar"):
        old["facts"].pop(k, None)
    old["facts"]["current_risk"] = {"terrascore": {"score": 88, "grade": "A"}}
    old["facts"]["track_record"] = {"n": 3}
    doc_schema(old)


def test_api_phat_lai_dung_tep_trong_kho():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/api/dossiers/schema")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/schema+json")
    assert r.content == open(PATH, "rb").read()


def test_script_doc_lap_buoc_0_lech_dinh_dang_chi_canh_bao(land_doc, capsys):
    """ops/verify_dossier.py: định dạng khớp → ĐẠT; lệch → LỆCH nhưng KHÔNG tính là hỏng (chữ ký mới quyết định)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vd", os.path.join(HERE, "..", "..", "ops", "verify_dossier.py"))
    vd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vd)
    rep = vd.Report()
    vd.check_format(land_doc, _schema(), rep)
    assert rep.fail == 0 and rep.warn == 0
    bad = copy.deepcopy(land_doc)
    bad["facts"]["predictions_included"] = True
    rep = vd.Report()
    vd.check_format(bad, _schema(), rep)
    assert rep.fail == 0 and rep.warn == 1 and "LỆCH" in capsys.readouterr().out
    rep = vd.Report()
    vd.check_format(land_doc, None, rep)
    assert rep.fail == 0 and rep.warn == 0
