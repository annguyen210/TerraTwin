"""Hồ sơ vườn chuẩn EUDR: kiểm ranh theo chuẩn GeoJSON EU, quy tắc sàng lọc phá
rừng, lô thửa chạy nền, hồ sơ ký số.

Không chạm mạng: phần lấy bản đồ/ảnh vệ tinh được giả lập; kiểm ranh và quy tắc
kết luận là hàm thuần.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import eudr, eudr_forest, eudr_geo, reqlang


@pytest.fixture(autouse=True)
def _vi():
    reqlang.set_lang("vi")


def sq(lat, lon, d=0.0005, close=True):
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d]]
    return {"type": "Polygon", "coordinates": [ring + ([ring[0]] if close else [])]}


def fc(*feats):
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": p, "geometry": g} for p, g in feats]})


def codes(plot):
    return [i["code"] for i in plot["issues"]]


# ---------------------------------------------------------------- chuẩn GeoJSON EU

def test_ranh_hop_le_va_dien_tich_dung():
    p = eudr_geo.validate_geometry(sq(12.7, 108.05))
    assert p["valid"] and p["kind"] == "polygon"
    # 0,001° × 0,001° ở vĩ độ 12,7: ~110,6 m × ~108,6 m ≈ 1,20 ha (sai số phép chiếu < 0,5%)
    assert 1.19 < p["area_ha"] < 1.215
    assert p["centroid"] == {"lat": 12.7, "lon": 108.05}


def test_ranh_ho_tu_khep_va_ghi_ro():
    p = eudr_geo.validate_geometry(sq(12.7, 108.05, close=False))
    assert p["valid"] and "F_CLOSED" in codes(p)
    ring = p["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_ranh_tu_cat_hinh_so_8_bi_tu_choi_kem_vi_tri():
    g = {"type": "Polygon", "coordinates": [[[108.05, 12.7], [108.051, 12.701], [108.051, 12.7],
                                             [108.05, 12.701], [108.05, 12.7]]]}
    p = eudr_geo.validate_geometry(g)
    assert not p["valid"] and "E_SELF_INTERSECT" in codes(p)
    msg = next(i["message"] for i in p["issues"] if i["code"] == "E_SELF_INTERSECT")
    assert "12.700500" in msg and "108.050500" in msg


def test_da_giac_co_lo_bi_tu_choi():
    g = sq(12.7, 108.05, d=0.001)
    g["coordinates"].append([[108.0501, 12.7001], [108.0502, 12.7001], [108.0502, 12.7002], [108.0501, 12.7001]])
    p = eudr_geo.validate_geometry(g)
    assert not p["valid"] and "E_HOLES" in codes(p)


def test_dao_kinh_do_vi_do_tu_sua():
    p = eudr_geo.validate_geometry({"type": "Point", "coordinates": [12.712345, 108.061234]}, area_declared=1)
    assert p["valid"] and "F_SWAPPED" in codes(p)
    assert p["geometry"]["coordinates"] == [108.061234, 12.712345]


def test_diem_tren_4ha_phai_khai_da_giac():
    p = eudr_geo.validate_geometry({"type": "Point", "coordinates": [108.061234, 12.712345]}, area_declared=6)
    assert not p["valid"] and "E_POINT_OVER_4HA" in codes(p)


def test_diem_khong_khai_dien_tich_eu_mac_dinh_4ha():
    p = eudr_geo.validate_geometry({"type": "Point", "coordinates": [108.061234, 12.712345]})
    assert p["valid"] and "W_POINT_NO_AREA" in codes(p)
    assert p["area_ha"] == 4.0 and p["area_source"] == "eu_default"


def test_duong_ke_khong_duoc_nhan():
    p = eudr_geo.validate_geometry({"type": "LineString", "coordinates": [[108, 12], [108.1, 12.1]]})
    assert not p["valid"] and codes(p) == ["E_GEOM_TYPE"]


def test_canh_bao_it_chu_so_thap_phan_doc_tu_van_ban_goc():
    text = ('{"type":"Feature","properties":{"ProductionPlace":"A","Area":1},'
            '"geometry":{"type":"Point","coordinates":[108.0612,12.7123]}}')
    p = eudr_geo.validate_text(text, "a.geojson")["plots"][0]
    assert p["valid"] and "W_PRECISION" in codes(p)
    text6 = text.replace("108.0612", "108.061200").replace("12.7123", "12.712300")
    assert "W_PRECISION" not in codes(eudr_geo.validate_text(text6, "a.geojson")["plots"][0])


def test_hai_thua_chong_nhau_va_trung_het():
    r = eudr_geo.validate_text(fc(({"ProductionPlace": "A"}, sq(12.7, 108.05)),
                                  ({"ProductionPlace": "B"}, sq(12.7004, 108.0504)),
                                  ({"ProductionPlace": "C"}, sq(12.75, 108.05)),
                                  ({"ProductionPlace": "D"}, sq(12.75, 108.05))))
    a, b, c, d = r["plots"]
    assert "E_OVERLAP" in codes(a) and "E_OVERLAP" in codes(b)
    assert "E_DUPLICATE" in codes(c) and "E_DUPLICATE" in codes(d)
    assert not any(p["valid"] for p in r["plots"])
    assert r["summary"]["n_errors"] == 4 and not r["summary"]["eu_ready"]


def test_mep_chong_nhe_chi_canh_bao():
    r = eudr_geo.validate_text(fc(({"ProductionPlace": "A"}, sq(12.7, 108.05)),
                                  ({"ProductionPlace": "B"}, sq(12.7, 108.05098))))
    assert all(p["valid"] for p in r["plots"])
    assert "W_OVERLAP_EDGE" in codes(r["plots"][0])


def test_csv_excel_viet_nam_va_wkt():
    r = eudr_geo.validate_text("ma;vi_do;kinh_do;dien_tich\nH1;12,712345;108,061234;1,2\n", "a.csv")
    p = r["plots"][0]
    assert p["valid"] and p["area_ha"] == 1.2 and p["geometry"]["coordinates"] == [108.061234, 12.712345]
    w = 'ma,wkt\nW1,"POLYGON((108.04 12.70, 108.042 12.70, 108.042 12.702, 108.04 12.702, 108.04 12.70))"\n'
    p = eudr_geo.validate_text(w, "a.csv")["plots"][0]
    assert p["valid"] and p["kind"] == "polygon" and 4.7 < p["area_ha"] < 4.9


def test_kml_va_chan_bom_xml():
    kml = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
           '<name>Vườn 1</name><Polygon><outerBoundaryIs><LinearRing><coordinates>108.040000,12.700000,0 '
           '108.042000,12.700000,0 108.042000,12.702000,0 108.040000,12.702000,0 108.040000,12.700000,0'
           '</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>')
    p = eudr_geo.validate_text(kml, "v.kml")["plots"][0]
    assert p["ref"] == "Vườn 1" and p["valid"] and "W_PRECISION" not in codes(p)
    bad = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><kml>&a;</kml>'
    r = eudr_geo.validate_text(bad, "b.kml")
    assert r["plots"] == [] and r["file_errors"][0]["code"] == "E_KML_UNSAFE"


def test_xuat_dung_mau_traces():
    r = eudr_geo.validate_text(fc(({"ProductionPlace": "A", "ProducerName": "Nguyễn Văn A"},
                                   # cố ý viết theo chiều KIM ĐỒNG HỒ
                                   {"type": "Polygon", "coordinates": [[[108.05, 12.7], [108.05, 12.701],
                                                                        [108.0512345678, 12.701], [108.05, 12.7]]]}),
                                  ({"ProductionPlace": "P", "Area": 1.5}, {"type": "Point", "coordinates": [108.1, 12.8]}),
                                  ({"ProductionPlace": "Q"}, {"type": "Point", "coordinates": [108.2, 12.8]}),
                                  ({"ProductionPlace": "X"}, {"type": "LineString", "coordinates": [[108, 12], [108.1, 12]]})))
    out = eudr_geo.to_eu_geojson(r["plots"])
    assert out["type"] == "FeatureCollection" and len(out["features"]) == 3   # đường kẻ bị loại
    a, p, q = out["features"]
    assert a["properties"] == {"ProducerName": "Nguyễn Văn A", "ProducerCountry": "VN", "ProductionPlace": "A"}
    ring = a["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert all(len(str(v).split(".")[1]) <= 6 for pt in ring for v in pt)
    from shapely.geometry import Polygon
    assert Polygon(ring).exterior.is_ccw                                     # RFC 7946
    assert p["properties"]["Area"] == 1.5 and "Area" not in q["properties"]  # điểm không khai: để EU tự mặc định


def test_tep_qua_25mb_bi_tu_choi(monkeypatch):
    monkeypatch.setattr(eudr_geo, "EU_MAX_FILE_BYTES", 100)
    r = eudr_geo.validate_text(fc(({"ProductionPlace": "A"}, sq(12.7, 108.05))), "a.geojson")
    assert r["file_errors"][0]["code"] == "E_FILE_SIZE"


# ---------------------------------------------------------------- quy tắc sàng lọc

TRAJ0 = {y: 0.0 for y in eudr_forest.IO_YEARS}


def test_ca_phe_che_bong_mot_ban_do_thay_cay_van_dat():
    # Đo thật 3/10/2026 gần Buôn Ma Thuột: WorldCover 76% tán cây, ALOS 0%, IO 0%.
    lv, why, sig = eudr_forest.verdict({"wc2020": 75.7, "alos2020": 0.0, "io": 0.0}, TRAJ0, 0.68, 0.65, [])
    assert lv == "low" and "1/3" in why[0] and sig["votes"] == ["wc2020"]


def test_hai_ban_do_thay_rung_khong_mat_cay_can_xem_lai():
    lv, _, _ = eudr_forest.verdict({"wc2020": 90.0, "alos2020": 31.0, "io": 8.0}, TRAJ0, 0.78, 0.75, [])
    assert lv == "review"


def test_rung_2020_roi_mat_cay_la_rui_ro():
    traj = {2017: 100, 2018: 100, 2019: 90, 2020: 95, 2021: 40, 2022: 10, 2023: 0}
    lv, why, sig = eudr_forest.verdict({"wc2020": 95.0, "alos2020": 80.0, "io": 95.0}, traj, 0.8, 0.45, [])
    assert lv == "high" and set(sig["loss_by"]) == {"io", "ndvi"}
    assert "2018–2020" in why[0]


def test_io_nhay_nam_qua_nam_khong_thanh_mat_rung_gia():
    # Yok Đôn thật: 2017 cây, 2018 cỏ, 2019 25%, 2020 cỏ, 2022 cây, 2023 cỏ.
    traj = {2017: 100, 2018: 0, 2019: 25, 2020: 0, 2021: 0, 2022: 100, 2023: 0}
    _, _, sig = eudr_forest.verdict({"wc2020": 90.0, "alos2020": 31.0, "io": 8.3}, traj, 0.78, 0.75, [])
    assert not sig["loss"]


def test_mot_ban_do_va_mat_cay_can_xem_lai():
    traj = {2017: 0, 2018: 0, 2019: 0, 2020: 0, 2021: 0, 2022: 0, 2023: 0}
    lv, _, _ = eudr_forest.verdict({"wc2020": 60.0, "alos2020": 0.0, "io": 0.0}, traj, 0.75, 0.4, [])
    assert lv == "review"


def test_chi_hai_ban_do_bat_dong_can_xem_lai_thieu_hon_hai_thi_chua_du():
    assert eudr_forest.verdict({"wc2020": 60.0, "alos2020": None, "io": 0.0}, TRAJ0, None, None, [])[0] == "review"
    assert eudr_forest.verdict({"wc2020": 60.0, "alos2020": None, "io": None}, {}, None, None, [])[0] == "unknown"


def test_trong_khu_bao_ton_khong_bao_gio_dat_thang():
    lv, why, _ = eudr_forest.verdict({"wc2020": 0.0, "alos2020": 0.0, "io": 0.0}, TRAJ0, 0.3, 0.3,
                                     ["Vườn quốc gia Yok Đôn"])
    assert lv == "review" and "Yok Đôn" in why[-1]


def test_cua_so_anh_cung_mua():
    (b0, b1, bp), (a0, a1, ap) = eudr_forest.s2_windows(date(2026, 10, 3))
    assert (b0, b1, bp) == (date(2020, 11, 1), date(2021, 2, 28), date(2020, 12, 31))
    assert (a0, a1, ap) == (date(2025, 11, 1), date(2026, 2, 28), date(2025, 12, 31))
    assert eudr_forest.s2_windows(date(2026, 2, 10))[1][0] == date(2024, 11, 1)


def _fake_sources(monkeypatch, wc=75.0, alos=0.0, io=0.0, ndvi=(0.68, 0.66), protected=()):
    def share(collection, year, asset, codes, res, geom, nodata=(0,)):
        v = {"esa-worldcover": wc, "alos-fnf-mosaic": alos, "io-lulc-annual-v02": io}[collection]
        return {"pct": v, "pixels": 144, "items": [f"{collection}-{year}"], "buffered_m": 0.0, "classes": {}}
    monkeypatch.setattr(eudr_forest, "class_share", share)
    it = iter(ndvi)
    monkeypatch.setattr(eudr_forest, "s2_scene", lambda geom, a, b, prefer=None: {
        "item": "S2X", "date": prefer.isoformat(), "clear_pct": 100.0, "ndvi_mean": next(it),
        "processing_baseline": "05.11", "image": {"url": "https://x/y.png", "bbox": [0, 0, 1, 1]}})
    monkeypatch.setattr(eudr_forest, "protected_areas", lambda lat, lon: {
        "checked": True, "inside": list(protected), "source": "OpenStreetMap"})
    from app.services import cache_store
    monkeypatch.setattr(cache_store, "get", lambda key: None)
    monkeypatch.setattr(cache_store, "put", lambda key, v, ttl_seconds: None)


def test_sang_loc_ghep_du_nguon(monkeypatch):
    _fake_sources(monkeypatch)
    r = eudr_forest.screen(eudr_geo.validate_geometry(sq(12.7, 108.05)))
    assert r["level"] == "low" and r["label"] == "Đạt sàng lọc"
    assert [f["id"] for f in r["forest_2020"]] == ["wc2020", "alos2020", "io"]
    assert r["forest_2020"][2]["items"] == ["io-lulc-annual-v02-2018", "io-lulc-annual-v02-2019",
                                            "io-lulc-annual-v02-2020"]
    assert len(r["io_trajectory"]) == 7 and r["s2"]["before"]["ndvi_mean"] == 0.68
    assert r["method"] == "terratwin.eudr-screen/1" and any("SÀNG LỌC" in c for c in r["caveats"])


def test_diem_sang_loc_tren_hinh_tron_va_ghi_ro(monkeypatch):
    _fake_sources(monkeypatch)
    p = eudr_geo.validate_geometry({"type": "Point", "coordinates": [108.061234, 12.712345]}, area_declared=1)
    g = eudr_geo.shapely_geom(p)
    assert 0.98 < eudr_geo.area_ha(g) < 1.01
    r = eudr_forest.screen(p)
    assert r["plot"]["geometry_used"] == "circle_from_point" and any("MỘT ĐIỂM" in c for c in r["caveats"])


def test_doi_ngon_ngu_luc_doc(monkeypatch):
    _fake_sources(monkeypatch)
    r = eudr_forest.screen(eudr_geo.validate_geometry(sq(12.7, 108.05)))
    reqlang.set_lang("en")
    en = eudr_forest._localize(r)
    assert en["label"] == "Passed screening" and "maps" in en["reasons"][0]


# ---------------------------------------------------------------- hồ sơ đất số không còn dự báo

def test_ho_so_dat_so_khong_ky_du_bao(monkeypatch):
    from app.services import dossier, landuse, passport
    monkeypatch.setattr(passport, "build", lambda lat, lon: {"available": True, "terrain": {"elev": 5},
                                                             "history": {"flood": {"events": 2}}})
    monkeypatch.setattr(landuse, "composition", lambda lat, lon: {"label": "Đất trồng trọt"})
    f = dossier.build_facts(10.0, 106.0, None, None)
    assert "current_risk" not in f and "track_record" not in f and "land_change" not in f
    assert f["predictions_included"] is False and f["evidence_classes"]["history_10y"] == "derived"


# ---------------------------------------------------------------- API

PW = "MatKhau123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'e.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setenv("TERRATWIN_EUDR_DELAY_S", "0")
    calls = []

    def fake_screen(plot):
        calls.append(plot["ref"])
        lv = "high" if plot["ref"].startswith("R") else "low"
        return {"method": eudr_forest.METHOD_VERSION, "cutoff": "2020-12-31", "level": lv,
                "label": eudr_forest.label(lv), "reasons": ["x"], "signals": {},
                "plot": {"geometry_used": "polygon"},
                "forest_2020": [{"id": "wc2020", "pct": 90.0 if lv == "high" else 0.0},
                                {"id": "alos2020", "pct": 80.0 if lv == "high" else 0.0},
                                {"id": "io", "pct": 90.0 if lv == "high" else 0.0}],
                "io_trajectory": [{"year": y, "tree_pct": (90.0 if y <= 2020 else 0.0) if lv == "high" else 0.0}
                                  for y in eudr_forest.IO_YEARS],
                "s2": {"before": None, "after": None}, "protected": {"checked": True, "inside": []}}
    monkeypatch.setattr(eudr_forest, "screen", fake_screen)
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        c.calls = calls
        yield c
    app.dependency_overrides.clear()


def _login(c, email="htx@vd.vn"):
    tok = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "HTX"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _drain():
    from app import db as dbmod
    from app.services import jobs_db
    with dbmod.SessionLocal() as s:
        while jobs_db.poll_and_run_one(s):
            pass


SET = fc(({"ProductionPlace": "V1", "ProducerName": "Hộ A"}, sq(12.70, 108.05)),
         ({"ProductionPlace": "R2", "ProducerName": "Hộ B"}, sq(12.72, 108.05)),
         ({"ProductionPlace": "SAI"}, {"type": "LineString", "coordinates": [[108, 12], [108.1, 12]]}))


def test_kiem_tep_va_xuat_khong_can_dang_nhap(env):
    c = env
    r = c.post("/api/eudr/validate", json={"text": SET, "filename": "a.geojson"}).json()
    assert r["summary"]["n"] == 3 and r["summary"]["n_valid"] == 2
    x = c.post("/api/eudr/export", json={"text": SET, "filename": "a.geojson"})
    assert x.status_code == 200 and x.headers["content-type"].startswith("application/geo+json")
    assert "attachment" in x.headers["content-disposition"]
    assert [f["properties"]["ProductionPlace"] for f in x.json()["features"]] == ["V1", "R2"]
    bad = c.post("/api/eudr/export", json={"geometry": {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}})
    assert bad.status_code == 422


def test_sang_loc_mot_thua_va_ranh_sai_thi_khong_goi_ve_tinh(env):
    c = env
    r = c.post("/api/eudr/screen", json={"geometry": sq(12.7, 108.05), "ref": "V"}).json()
    assert r["plot"]["valid"] and r["screening"]["level"] == "low"
    r = c.post("/api/eudr/screen", json={"geometry": {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}}).json()
    assert r["screening"] is None and c.calls == ["V"]


def test_phat_hanh_ho_so_vuon_ky_so_va_kiem_duoc(env):
    c = env
    d = c.post("/api/eudr/dossier", json={"geometry": sq(12.7, 108.05), "ref": "Vườn ông Ba",
                                          "producer": "Lê Văn Ba", "commodity": "coffee"}).json()
    f = d["facts"]
    assert f["kind"] == "eudr_plot" and f["schema"] == eudr.FACTS_SCHEMA and f["predictions_included"] is False
    assert f["plot"]["producer"] is None and f["plot"]["commodity_label"] == "Cà phê"   # ẩn mặc định
    assert d["disclosure"]["token"] and "producer" in f["disclosure"]["fields"]
    assert f["plot"]["geometry"]["type"] == "Polygon" and f["screening"]["level"] == "low"
    assert d["verification"]["valid"] and d["url"].endswith(f"/h/{d['id']}")
    again = c.get(f"/api/dossier/{d['id']}").json()
    assert again["facts"]["plot"]["ref"] == "Vườn ông Ba" and again["verification"]["valid"]
    bad = c.post("/api/eudr/dossier", json={"geometry": {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}})
    assert bad.status_code == 422


def test_lo_thua_can_dang_nhap(env):
    assert env.post("/api/eudr/sets", json={"text": SET}).status_code == 401


def test_lo_thua_day_du(env):
    c = env
    h = _login(c)
    r = c.post("/api/eudr/sets", json={"text": SET, "filename": "a.geojson", "title": "Vụ 2026",
                                       "commodity": "coffee", "producer": "HTX Ea Tu"}, headers=h).json()
    sid = r["set_id"]
    assert r["validation"]["n_valid"] == 2 and r["screening"] == 2
    assert c.post("/api/eudr/sets", json={"text": SET}, headers=h).status_code == 409   # một lô một lúc
    assert c.get(f"/api/eudr/sets/{sid}", headers=h).json()["state"] == "queued"

    _drain()
    d = c.get(f"/api/eudr/sets/{sid}", headers=h).json()
    assert d["state"] == "done" and d["summary"]["by_level"]["low"] == 1 and d["summary"]["by_level"]["high"] == 1
    assert d["summary"]["n_invalid"] == 1 and sorted(c.calls) == ["R2", "V1"]

    g = c.get(f"/api/eudr/sets/{sid}/geojson?which=passed", headers=h).json()
    assert [f["properties"]["ProductionPlace"] for f in g["features"]] == ["V1"]
    assert g["features"][0]["properties"]["ProducerName"] == "Hộ A"
    csv_text = c.get(f"/api/eudr/sets/{sid}/csv", headers=h).text
    assert csv_text.startswith("﻿") and "Rủi ro phá rừng" in csv_text and "SAI" in csv_text

    iss = c.post(f"/api/eudr/sets/{sid}/dossiers", headers=h).json()
    assert iss["n"] == 2
    assert c.post(f"/api/eudr/sets/{sid}/dossiers", headers=h).json()["n"] == 0        # không phát hành trùng
    one = c.get(f"/api/dossier/{iss['issued'][0]['id']}").json()
    assert one["facts"]["kind"] == "eudr_plot" and one["verification"]["valid"]

    other = _login(c, "khac@vd.vn")
    assert c.get(f"/api/eudr/sets/{sid}", headers=other).status_code == 404
    assert c.delete(f"/api/eudr/sets/{sid}", headers=h).status_code == 204
    assert c.get(f"/api/eudr/sets/{sid}", headers=h).status_code == 404


def test_phuong_phap_cong_khai(env):
    m = env.get("/api/eudr/method").json()
    assert m["rule_version"] == "terratwin.eudr-screen/1" and m["thresholds"]["forest_vote_pct"] == 10.0
    assert m["eu_rules"]["min_decimals"] == 6 and m["levels"]["high"] == "Rủi ro phá rừng"


def test_quy_tac_v2_vuon_cay_thua_khong_mat_cay_thi_dat():
    """v2: vườn cây lâu năm (ALOS xếp rừng 100%, WorldCover/IO thấy 10–45% tán) không mất cây
    → ĐẠT; v1 đẩy sang CẦN XEM LẠI (lý do M3 v1 chỉ 0,525)."""
    from app.services import eudr_forest as ef
    maps = {"wc2020": 47.2, "alos2020": 100.0, "io": 22.2}
    flat = {y: 20.0 for y in ef.IO_YEARS}
    assert ef.verdict(maps, flat, None, None, [], rule=1)[0] == "review"
    lv, reasons, sig = ef.verdict(maps, flat, None, None, [], rule=2)
    assert lv == "low" and "dưới 50%" in reasons[0] and sig["rule"] == "terratwin.eudr-screen/2"


def test_quy_tac_v2_rung_that_van_bi_co_va_khong_bao_gio_xau_hon_v1():
    from app.services import eudr_forest as ef
    flat = {y: 90.0 for y in ef.IO_YEARS}
    forest = {"wc2020": 100.0, "alos2020": 100.0, "io": 100.0}
    assert ef.verdict(forest, flat, None, None, [], rule=2)[0] == "review"
    # 1 bản đồ thấy rừng + mất cây → vẫn bị cờ ở v2
    lost = {y: (60.0 if y <= 2020 else 20.0) for y in ef.IO_YEARS}
    assert ef.verdict({"wc2020": 15.0, "alos2020": 0.0, "io": 60.0}, lost, None, None, [], rule=2)[0] in ("review", "high")
    # v2 không bao giờ nặng hơn v1 trên một lưới tổ hợp
    rank = {"low": 0, "review": 1, "high": 2, "unknown": 0}
    for a in (0, 15, 40, 60, 100):
        for b in (0, 15, 40, 60, 100):
            for c in (0, 15, 40, 60, 100):
                for traj in (flat, lost):
                    m = {"wc2020": float(a), "alos2020": float(b), "io": float(c)}
                    assert rank[ef.verdict(m, traj, None, None, [], rule=2)[0]] <= rank[ef.verdict(m, traj, None, None, [], rule=1)[0]]


def test_production_van_dung_quy_tac_v1_cho_toi_khi_v2_dat_kiem_dinh():
    from app.services import eudr_forest as ef
    assert ef.ACTIVE_RULE == 1 and ef.METHOD_VERSION == "terratwin.eudr-screen/1"


def test_v2_truot_duoc_cong_bo_va_production_khong_bat_v2(env):
    """Kết quả v2 (mẫu mới seed 20261006) đã có và TRƯỢT → phải hiện công khai trong lịch sử
    kiểm định, kèm quyết định và chẩn đoán; quy tắc đang chạy vẫn là v1. Nếu một ngày kết quả
    đổi thành đạt mà quên bật, hoặc bật v2 khi kết quả trượt, test này đỏ."""
    from app.services import eudr_forest as ef
    m = env.get("/api/eudr/method").json()
    hist = {h["sample"]: h for h in m["validation_history"]}
    assert set(hist) == {"v1", "v2"} and hist["v1"]["passed"] is False
    v2 = hist["v2"]
    assert v2["rule_version"] == "terratwin.eudr-screen/2" and v2["n"] == 120
    assert v2["passed"] is False and "KHÔNG bật" in v2["decision"]
    assert v2["metrics"]["M3_pass_clean"] < v2["pass_thresholds"]["M3_pass_clean"]
    assert "không thay đổi kết luận" in v2["post_hoc_diagnosis"]["label"]
    assert (ef.ACTIVE_RULE == 2) == bool(v2["passed"])
