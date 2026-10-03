"""Hạ tầng niềm tin đợt 3: cây Merkle RFC 6962, sổ minh bạch, tiết lộ chọn lọc, lô hàng
+ cân bằng khối lượng + chứng thư Merkle, đối chiếu sổ đỏ, trợ lý EUDR có trích dẫn,
giám sát sau phát hành, nhân chứng sổ. Không chạm mạng (sàng lọc vệ tinh giả lập).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import disclosure, eudr_assistant, eudr_forest, landdoc, merkle, monitor, reqlang


@pytest.fixture(autouse=True)
def _vi():
    reqlang.set_lang("vi")


# ---------------------------------------------------------------- Merkle

def test_merkle_vector_rfc6962():
    assert merkle.leaf_hash(b"").hex() == "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
    assert merkle.root([]).hex() == hashlib.sha256(b"").hexdigest()


def test_merkle_bang_chung_dung_moi_kich_thuoc_va_khong_nhan_nham():
    L = [merkle.leaf_hash(f"x{i}".encode()) for i in range(40)]
    for n in range(1, 40):
        r = merkle.root(L[:n])
        for i in range(n):
            p = merkle.inclusion_proof(i, L[:n])
            assert merkle.verify_inclusion(L[i], i, n, p, r)
            if n > 1:
                assert not merkle.verify_inclusion(L[(i + 1) % n], i, n, p, r)
        for m in range(1, n + 1):
            p = merkle.consistency_proof(m, L[:n])
            assert merkle.verify_consistency(m, n, merkle.root(L[:m]), r, p)
            if m < n:
                forged = L[:m - 1] + [merkle.leaf_hash(b"sua")] + L[m:n]
                assert not merkle.verify_consistency(m, n, merkle.root(L[:m]), merkle.root(forged), p)


def test_nhan_chung_dung_cung_thuat_toan_doc_lap():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "ops", "translog_witness.py")
    spec = importlib.util.spec_from_file_location("witness", path)
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    L = [merkle.leaf_hash(f"y{i}".encode()) for i in range(23)]
    for m in range(1, 23):
        p = merkle.consistency_proof(m, L)
        assert w.verify_consistency(m, 23, merkle.root(L[:m]), merkle.root(L), p)
        assert not w.verify_consistency(m, 23, merkle.root(L[:m]), merkle.root(L[:22] + [L[0]]), p)


# ---------------------------------------------------------------- tiết lộ chọn lọc

def test_tiet_lo_chon_loc():
    digest, priv = disclosure.commit("producer", "Nguyễn Văn A")
    assert len(digest) == 64 and "Nguyễn" not in digest
    tok = disclosure.encode_token({"producer": priv})
    back = disclosure.decode_token(tok)
    assert disclosure.reveal({"producer": digest}, back) == {"producer": {"value": "Nguyễn Văn A", "ok": True}}
    back["producer"]["value"] = "Trần Văn B"                     # đổi tên → lệch cam kết
    assert disclosure.reveal({"producer": digest}, back)["producer"]["ok"] is False


# ---------------------------------------------------------------- sổ đỏ

def test_so_do_rung_phong_ho_la_co_do():
    r = landdoc.check({"dien_tich_m2": "12.000", "ma_muc_dich": "RPH", "thoi_han": "lâu dài"}, 1.2)
    assert r["verdict"] == "red_flag" and r["label"] == "Cờ đỏ pháp lý"
    assert next(c for c in r["checks"] if c["id"] == "area")["ok"] is True


def test_so_do_cln_khop_va_ten_khong_dau():
    r = landdoc.check({"dien_tich_m2": 10500, "muc_dich": "Đất trồng cây lâu năm", "thoi_han": "2064-01-01",
                       "ten_chu": "NGUYEN VAN AN"}, 1.0, "Nguyễn Văn An", today=date(2026, 10, 3))
    assert r["fields"]["ma_muc_dich"] == "CLN" and r["verdict"] == "ok"


def test_so_do_het_han_lech_dien_tich_rung_san_xuat_can_xem():
    r = landdoc.check({"dien_tich_m2": 5000, "ma_muc_dich": "RSX", "thoi_han": "2020-05-01"}, 1.5,
                      today=date(2026, 10, 3))
    by = {c["id"]: c["ok"] for c in r["checks"]}
    assert by == {"area": False, "land_use": None, "term": False} and r["verdict"] == "review"


def test_doc_so_do_bang_llm_gia_lap(monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm, "complete_vision", lambda *a, **k: (
        'Kết quả: {"so_thua": "123", "to_ban_do": "45", "dien_tich_m2": "1.234,5", "ma_muc_dich": "cln", '
        '"muc_dich": "Đất trồng cây lâu năm", "thoi_han": "lâu dài", "ten_chu": "Lê Thị C", "confidence": 0.9}'))
    f = landdoc.extract("eA==")
    assert f["dien_tich_m2"] == 1234.5 and f["ma_muc_dich"] == "CLN" and f["confidence"] == 0.9


# ---------------------------------------------------------------- trợ lý EUDR

@pytest.mark.parametrize("q,want", [
    ("vườn 3 ha có phải vẽ ranh không", "eudr-art2-27-28"),
    ("cao su có phải rừng không", "eudr-art2-5-6"),
    ("phạt bao nhiêu", "eudr-art25"),
    ("toa do can bao nhieu chu so", "eudr-art2-27-28"),
    ("đất rừng phòng hộ trồng cà phê được không", "vn-land-codes"),
])
def test_tro_ly_tim_dung_dieu_khoan(q, want):
    r = eudr_assistant.ask(q)
    assert r["citations"][0]["id"] == want and r["mode"] == "extractive" and f"[{want}]" in r["answer"]


def test_tro_ly_tu_choi_cau_ngoai_pham_vi():
    for q in ("giá cà phê hôm nay", "thời tiết Đà Lạt mai thế nào"):
        assert eudr_assistant.ask(q)["mode"] == "none"


def test_tro_ly_llm_phai_trich_dung_doan(monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Thửa trên 4 ha phải vẽ đa giác [eudr-art2-27-28].")
    assert eudr_assistant.ask("vườn 3 ha có phải vẽ ranh không")["mode"] == "llm"
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Bịa không trích dẫn.")
    assert eudr_assistant.ask("vườn 3 ha có phải vẽ ranh không")["mode"] == "extractive"


# ---------------------------------------------------------------- giám sát

def test_so_sanh_giam_sat():
    assert monitor.compare({"level": "low", "signals": {}}, {"level": "review", "signals": {}}) == (True, ["low→review"])
    assert monitor.compare({"level": "low", "signals": {"loss": False}},
                           {"level": "low", "signals": {"loss": True}}) == (True, ["new_tree_loss"])
    assert monitor.compare({"level": "review"}, {"level": "low"})[0] is False


# ---------------------------------------------------------------- API

PW = "MatKhau123"


def sq(lat, lon, d=0.0005):
    return {"type": "Polygon", "coordinates": [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
                                                [lon - d, lat + d], [lon - d, lat - d]]]}


def _fake_screen(level_by_ref):
    def f(plot):
        lv = level_by_ref.get(plot.get("ref"), "low")
        return {"method": eudr_forest.METHOD_VERSION, "cutoff": "2020-12-31", "level": lv,
                "label": eudr_forest.label(lv), "reasons": ["x"], "signals": {"loss": lv == "high"},
                "plot": {"geometry_used": "polygon"}, "forest_2020": [{"id": "wc2020", "pct": 0.0}],
                "io_trajectory": [], "s2": {"before": None, "after": None},
                "protected": {"checked": True, "inside": []}, "caveats": []}
    return f


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    levels = {}
    monkeypatch.setattr(eudr_forest, "screen", _fake_screen(levels))
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        c.levels, c.Session = levels, Session
        yield c
    app.dependency_overrides.clear()


def _login(c, email="dn@vd.vn"):
    tok = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "DN"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _issue(c, ref, lat, h=None, **kw):
    c.levels[ref] = kw.pop("level", "low")
    body = {"geometry": sq(lat, 108.05), "ref": ref, "producer": "Lê Văn Ba", "commodity": "coffee", **kw}
    r = c.post("/api/eudr/dossier", json=body, headers=h or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_ho_so_an_ten_chu_ho_va_tiet_lo_khi_co_link(env):
    c = env
    d = _issue(c, "V1", 12.70)
    assert d["facts"]["plot"]["producer"] is None
    assert "Lê Văn Ba" not in json.dumps(d["facts"], ensure_ascii=False)
    assert d["verification"]["valid"] and d["disclosure"]["stored"] is False
    full = c.get(f"/api/dossier/{d['id']}?d={d['disclosure']['token']}").json()
    assert full["revealed"]["producer"] == {"value": "Lê Văn Ba", "ok": True}
    shown = _issue(c, "V2", 12.71, hide_producer=False)
    assert shown["facts"]["plot"]["producer"] == "Lê Văn Ba"
    assert set(shown["facts"]["disclosure"]["fields"]) == {"owner_key"}       # chỉ khoá chủ hồ sơ, không giấu tên


def test_ho_so_kem_so_do_doi_chieu_lai_o_may_chu(env):
    c = env
    d = _issue(c, "V3", 12.72, land_document={"fields": {"dien_tich_m2": 12000, "ma_muc_dich": "RPH",
                                                         "ten_chu": "Lê Văn Ba"},
                                              "image_sha256": "a" * 64, "source": "manual"})
    ld = d["facts"]["land_document"]
    assert ld["verdict"] == "red_flag" and ld["image_sha256"] == "a" * 64 and ld["evidence_class"] == "declared"
    assert "ten_chu" not in ld["fields"] and "land_owner" in d["facts"]["disclosure"]["fields"]


def test_tai_ve_mang_chuoi_da_bam_va_khoa_cong_khai(env):
    c = env
    d = _issue(c, "V4", 12.73)
    assert hashlib.sha256(d["facts_canonical"].encode()).hexdigest() == d["proof"]["facts_hash"]
    assert json.loads(d["facts_canonical"]) == d["facts"] and d["proof"]["public_key_b64"]
    assert hashlib.sha256(d["proof"]["entry_message"].encode()).hexdigest() == d["proof"]["entry_hash"]


def test_so_minh_bach_dau_cay_on_dinh_va_bang_chung(env):
    c = env
    for i in range(5):
        _issue(c, f"L{i}", 12.6 + i / 100)
    h1 = c.get("/api/log/sth").json()
    assert h1["tree_size"] == 5 and c.get("/api/log/sth").json() == h1          # cùng kích thước: cùng đầu cây
    _issue(c, "L5", 12.9)
    h2 = c.get("/api/log/sth").json()
    p = c.get("/api/log/consistency?first=5&second=6").json()
    assert merkle.verify_consistency(5, 6, bytes.fromhex(h1["root_hash"]), bytes.fromhex(h2["root_hash"]),
                                     merkle.unhex(p["proof"]))
    inc = c.get("/api/log/inclusion?seq=3").json()
    assert merkle.verify_inclusion(bytes.fromhex(inc["leaf_hash"]), 2, 6, merkle.unhex(inc["proof"]),
                                   bytes.fromhex(h2["root_hash"]))
    page = c.get("/api/dossier/" + c.get("/api/dossiers/log").json()["entries"][0]["entry_hash"][:0] + "x")
    assert page.status_code == 404
    from app.services import translog
    with c.Session() as s:
        assert translog.verify_head(s, h2)


def test_lo_hang_can_bang_khoi_luong_va_chung_thu(env):
    c = env
    h = _login(c)
    a = _issue(c, "VA", 12.80, h)                       # ~1,2 ha → trần cà phê 6 t/ha ≈ 7.200 kg
    b = _issue(c, "VB", 12.81, h, level="review")
    x = _issue(c, "VX", 12.82, h, level="high")
    r = c.post("/api/lots", headers=h, json={"ref": "LOT-1", "commodity": "coffee", "season": "2026/27",
                                             "operator": "Cty A", "deliveries": [
        {"dossier_id": a["id"], "kg": 3000}, {"dossier_id": a["id"], "kg": 1000},     # gộp trùng = 4.000
        {"dossier_id": b["id"], "kg": 500}, {"dossier_id": x["id"], "kg": 500}]}).json()
    rows = {row["dossier_id"]: row for row in r["checks"]["rows"]}
    assert rows[a["id"]]["status"] == "ok" and rows[a["id"]]["kg"] == 4000
    assert rows[b["id"]]["status"] == "blocked" and rows[x["id"]]["status"] == "blocked"
    assert not r["checks"]["certifiable"]
    lid = r["id"]
    assert c.post(f"/api/lots/{lid}/certify", headers=h).status_code == 422

    r = c.put(f"/api/lots/{lid}", headers=h, json={"ref": "LOT-1", "commodity": "coffee", "season": "2026/27",
                                                   "operator": "Cty A", "deliveries": [
        {"dossier_id": a["id"], "kg": 4000},
        {"dossier_id": b["id"], "kg": 500, "review_ack": "Đã xem ảnh thực địa: cà phê che bóng muồng đen"}]}).json()
    assert r["checks"]["certifiable"] and r["checks"]["n_warning"] == 1
    cert = c.post(f"/api/lots/{lid}/certify", headers=h).json()
    f = cert["certificate"]["facts"]
    assert f["kind"] == "lot_certificate" and f["lot"]["quantity_kg"] == 4500 and f["lot"]["hs_code"] == "0901"
    assert f["merkle"]["size"] == 2 and a["id"] not in json.dumps(f)          # không lộ danh sách nhà cung cấp
    assert cert["certificate"]["verification"]["valid"]

    pr = c.get(f"/api/lot-proof/{cert['lot']['certificate_id']}/{a['id']}").json()
    from app.services import lots
    leaf = merkle.leaf_hash(lots.leaf_data(pr["leaf"]))
    assert merkle.verify_inclusion(leaf, pr["leaf_index"], pr["tree_size"], merkle.unhex(pr["proof"]),
                                   bytes.fromhex(f["merkle"]["root"]))
    dds = c.get(f"/api/lots/{lid}/dds", headers=h).json()
    assert dds["draft"] and dds["commodity"]["net_mass_kg"] == 4500 and len(dds["geolocation"]["features"]) == 2
    assert dds["geolocation_valid"]

    # Vườn VA bán tiếp cho DOANH NGHIỆP KHÁC cùng vụ: cộng dồn vượt trần → chặn.
    h2 = _login(c, "dn2@vd.vn")
    r2 = c.post("/api/lots", headers=h2, json={"ref": "LOT-2", "commodity": "coffee", "season": "2026/27",
                                               "deliveries": [{"dossier_id": a["id"], "kg": 4000}]}).json()
    row = r2["checks"]["rows"][0]
    assert row["status"] == "blocked" and row["other_lots_kg"] == 4000 and "Vượt năng suất trần" in row["notes"][0]

    # Lô NHÁP của người khác không được "giữ chỗ" sức sản xuất của vườn (chống lạm dụng).
    h3 = _login(c, "dn3@vd.vn")
    c.post("/api/lots", headers=h3, json={"season": "2027/28", "deliveries": [{"dossier_id": a["id"], "kg": 7000}]})
    r4 = c.post("/api/lots", headers=h2, json={"season": "2027/28", "deliveries": [{"dossier_id": a["id"], "kg": 3000}]}).json()
    assert r4["checks"]["rows"][0]["other_lots_kg"] == 0 and r4["checks"]["rows"][0]["status"] == "ok"


def test_giam_sat_chan_lo_khi_vuon_xau_di(env):
    c = env
    h = _login(c, "gs@vd.vn")
    a = _issue(c, "VM", 12.85, h)
    from app.services import monitor as mon
    with c.Session() as s:
        out = mon.run(s, screen=_fake_screen({"VM": "high"}), radar=lambda p: {"signal": "none"})
    assert out == {"checked": 1, "changed": 1, "candidates": 1}
    page = c.get(f"/api/dossier/{a['id']}").json()
    assert page["monitor"]["changed"] and page["monitor"]["level"] == "high"
    r = c.post("/api/lots", headers=h, json={"season": "2026/27", "deliveries": [{"dossier_id": a["id"], "kg": 10}]}).json()
    assert r["checks"]["rows"][0]["status"] == "blocked"
    with c.Session() as s:                                      # vừa kiểm → không kiểm lại ngay
        assert mon.run(s, screen=_fake_screen({}), radar=lambda p: None)["checked"] == 0


def test_hoi_dap_va_doi_chieu_so_do_qua_api(env):
    c = env
    r = c.post("/api/eudr/ask", json={"q": "phạt bao nhiêu"}).json()
    assert r["citations"][0]["id"] == "eudr-art25"
    k = c.post("/api/landdoc/check", json={"fields": {"dien_tich_m2": 9500, "ma_muc_dich": "CLN"}, "area_ha": 1.0}).json()
    assert {x["id"]: x["ok"] for x in k["checks"]}["area"] is True
    h = _login(c, "so@vd.vn")
    from app.services import llm
    if not llm.available():
        e = c.post("/api/landdoc/extract", headers=h, json={"data_b64": "aGVsbG8gd29ybGQ=", "media_type": "image/jpeg"})
        assert e.status_code == 503 and len(e.json()["detail"]["image_sha256"]) == 64


def test_nong_ho_xac_nhan_hoac_tu_choi_dot_giao_hang(env):
    c = env
    h = _login(c, "xn@vd.vn")
    a = _issue(c, "VXN", 12.88, h)
    tok = a["disclosure"]["token"]
    assert "owner_key" in a["facts"]["disclosure"]["fields"]
    lot = c.post("/api/lots", headers=h, json={"ref": "L-XN", "season": "2028/29", "operator": "Cty X",
                                                "deliveries": [{"dossier_id": a["id"], "kg": 2000}]}).json()
    assert c.get(f"/api/dossier/{a['id']}/deliveries?d=sai").status_code == 403         # không có khoá chủ
    pend = c.get(f"/api/dossier/{a['id']}/deliveries?d={tok}").json()["deliveries"]
    assert pend == [{"lot_id": lot["id"], "lot_ref": "L-XN", "operator": "Cty X", "season": "2028/29",
                     "commodity": "Cà phê", "kg": 2000.0, "date": None, "lot_state": "draft", "confirmation": None}]

    # Nông hộ từ chối → đợt giao bị chặn khỏi lô.
    r = c.post(f"/api/dossier/{a['id']}/deliveries/{lot['id']}", json={"d": tok, "action": "reject"}).json()
    assert r["confirmation"]["status"] == "rejected"
    chk = c.put(f"/api/lots/{lot['id']}", headers=h, json={"ref": "L-XN", "season": "2028/29",
                                                           "deliveries": [{"dossier_id": a["id"], "kg": 2000}]}).json()
    assert chk["checks"]["rows"][0]["status"] == "blocked" and "TỪ CHỐI" in chk["checks"]["rows"][0]["notes"][0]

    # Xác nhận → giữ khi sửa lô cùng số kg; lô nháp ĐÃ xác nhận thì được tính vào sức sản xuất.
    c.post(f"/api/dossier/{a['id']}/deliveries/{lot['id']}", json={"d": tok, "action": "confirm"})
    chk = c.put(f"/api/lots/{lot['id']}", headers=h, json={"ref": "L-XN", "season": "2028/29",
                                                           "deliveries": [{"dossier_id": a["id"], "kg": 2000}]}).json()
    assert chk["checks"]["rows"][0]["producer_confirmation"] == "confirmed" and chk["checks"]["n_confirmed"] == 1
    h2 = _login(c, "xn2@vd.vn")
    other = c.post("/api/lots", headers=h2, json={"season": "2028/29", "deliveries": [{"dossier_id": a["id"], "kg": 100}]}).json()
    assert other["checks"]["rows"][0]["other_lots_kg"] == 2000


def test_tong_quan_va_so_lieu_cong_khai(env):
    c = env
    h = _login(c, "tq@vd.vn")
    a = _issue(c, "VTQ", 12.9, h)
    c.post("/api/lots", headers=h, json={"season": "2029/30", "deliveries": [{"dossier_id": a["id"], "kg": 100}]})
    o = c.get("/api/eudr/overview", headers=h).json()
    assert o["lots"] == 1 and o["deliveries_pending_confirmation"] == 1
    s = c.get("/api/eudr/public-stats").json()
    assert s["plot_dossiers"] >= 1 and s["log_size"] >= s["plot_dossiers"]


def test_giam_sat_radar_manh_danh_dau_thay_doi(env):
    c = env
    h = _login(c, "rd@vd.vn")
    a = _issue(c, "VRD", 12.95, h)
    from app.services import monitor as mon
    with c.Session() as s:
        out = mon.run(s, screen=_fake_screen({"VRD": "low"}),
                      radar=lambda p: {"signal": "strong", "drop_db": 4.2, "label": "x"})
    assert out["changed"] == 1
    m = c.get(f"/api/dossier/{a['id']}").json()["monitor"]
    assert m["changed"] and "radar_drop" in m["why"] and m["radar"]["drop_db"] == 4.2


def test_bang_tin_hom_nay(env):
    c = env
    pub = c.get("/api/today").json()
    assert not pub["signed_in"] and pub["deadlines"][0]["date"] == "2026-12-30" and pub["tip"]["id"]
    h = _login(c, "hn@vd.vn")
    a = _issue(c, "VHN", 12.97, h)
    c.post("/api/lots", headers=_login(c, "hn2@vd.vn"), json={"operator": "Cty B", "season": "2030/31",
                                                               "deliveries": [{"dossier_id": a["id"], "kg": 500}]})
    me = c.get("/api/today", headers=h).json()
    assert me["signed_in"] and me["counts"]["eudr_dossiers"] == 1
    assert any(i["kind"] == "delivery" and "Cty B" in i["title"] for i in me["items"])


def test_429_co_header_cors_va_preflight_khong_tinh(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "_RATE", 2)
    main._HITS.clear()
    c = TestClient(main.app)
    h = {"Origin": "http://localhost:1825"}
    for _ in range(3):
        c.options("/api/eudr/method", headers={**h, "Access-Control-Request-Method": "GET"})
    codes = [c.get("/api/eudr/method", headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = c.get("/api/eudr/method", headers=h)
    assert r.status_code == 429 and r.headers.get("access-control-allow-origin") in ("*", "http://localhost:1825")
    main._HITS.clear()


def test_xoa_tai_khoan_xoa_du_lieu_ca_nhan_eudr(env):
    c = env
    h = _login(c, "xoa@vd.vn")
    a = _issue(c, "VXOA", 12.99, h)
    c.post("/api/eudr/sets", headers=h, json={"text": SET_ONE, "filename": "a.geojson"})
    c.post("/api/lots", headers=h, json={"season": "2031/32", "deliveries": [{"dossier_id": a["id"], "kg": 10}]})
    from app.db import Dossier, EudrSet, Lot
    with c.Session() as s:
        assert s.get(Dossier, a["id"]).private_json
    assert c.delete("/api/account", headers=h).status_code == 204
    with c.Session() as s:
        d = s.get(Dossier, a["id"])
        assert d is not None and d.user_id is None and d.private_json is None   # hồ sơ ở lại sổ, tên thật thì không
        assert s.query(EudrSet).count() == 0 and s.query(Lot).count() == 0
    assert c.get(f"/api/dossier/{a['id']}").json()["verification"]["valid"]


SET_ONE = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"ProductionPlace": "X", "ProducerName": "Hộ X"},
                       "geometry": sq(12.6, 108.0)}]})


def test_han_muc_phat_hanh_an_danh(env, monkeypatch):
    from app.services import quota
    c = env
    quota.reset()
    monkeypatch.setitem(quota.LIMITS, "dossier", (2, 300, 86_400))
    assert _issue(c, "Q1", 12.31)["id"] and _issue(c, "Q2", 12.32)["id"]
    r = c.post("/api/eudr/dossier", json={"geometry": sq(12.33, 108.05), "ref": "Q3", "commodity": "coffee"})
    assert r.status_code == 429 and "đăng nhập" in r.json()["detail"] and int(r.headers["retry-after"]) > 0
    h = _login(c, "qh@vd.vn")
    assert _issue(c, "Q4", 12.34, h)["id"]                     # đăng nhập: hạn mức riêng, cao hơn
    quota.reset()
