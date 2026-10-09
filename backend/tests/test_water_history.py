"""Lịch sử nước radar: quy tắc cảnh có nước, nền của chính thửa, ghép đợt, chọn quỹ đạo, cổng chặn bật."""
from __future__ import annotations

import json


def _rows(seq):
    """seq: [(ngày, p50, p25, p10)] — p75 không dùng."""
    return [{"date": d, "p10": p10, "p25": p25, "p50": p50, "p75": p50 + 2, "mean": p50} for d, p50, p25, p10 in seq]


def test_canh_co_nuoc_phai_vuot_nguong_tuyet_doi_va_tut_so_voi_nen():
    from app.services import water_history as wh
    base = {"p10": -11.0, "p25": -10.0, "p50": -8.0, "p75": -6.0}
    assert wh.flag({"p10": -21, "p25": -20, "p50": -18.5}, base) == "≥50%"
    assert wh.flag({"p10": -21, "p25": -19, "p50": -16}, base) == "25–50%"
    assert wh.flag({"p10": -19, "p25": -14, "p50": -9}, base) == "10–25%"
    assert wh.flag({"p10": -13, "p25": -11, "p50": -9}, base) is None
    # mặt nước THƯỜNG TRỰC (hồ): nền đã tối → không phải "đợt lũ" mỗi lần chụp
    lake = {"p10": -24.0, "p25": -23.0, "p50": -22.0, "p75": -20.0}
    assert wh.flag({"p10": -24, "p25": -23, "p50": -22.5}, lake) is None


def test_ghep_dot_va_muc_phu_cao_nhat():
    from app.services import water_history as wh
    rows = _rows([("2020-09-28", -8, -10, -11), ("2020-10-10", -16.7, -18.5, -20), ("2020-10-13", -18.3, -19.8, -21),
                  ("2020-10-25", -9, -12, -13), ("2020-11-15", -14.4, -16.9, -19), ("2021-03-01", -8, -10, -11)])
    base = {"p10": -11.0, "p25": -10.0, "p50": -8.0, "p75": -6.0}
    ev = wh.events(rows, base)
    assert len(ev) == 2
    assert ev[0]["start"] == "2020-10-10" and ev[0]["end"] == "2020-10-13" and ev[0]["peak_cover"] == "≥50%"
    assert ev[0]["n_scenes"] == 2 and ev[0]["min_p50_db"] == -18.3
    assert ev[1]["start"] == "2020-11-15" and ev[1]["peak_cover"] == "10–25%"   # cách >24 ngày → đợt riêng


def test_nen_la_trung_vi_theo_thoi_gian():
    from app.services import water_history as wh
    rows = _rows([("2020-01-01", -8, -10, -11), ("2020-02-01", -9, -11, -12), ("2020-10-10", -19, -21, -22)])
    assert wh.baseline(rows)["p50"] == -9.0


def test_chon_mot_quy_dao_va_mot_canh_moi_ngay():
    from app.services import water_history as wh
    def it(d, orbit, rel, i):
        return {"id": f"x{i}", "properties": {"datetime": d + "T10:00:00Z", "sat:orbit_state": orbit, "sat:relative_orbit": rel}}
    items = [it("2020-10-10", "descending", 18, 1), it("2020-10-10", "descending", 18, 2), it("2020-10-22", "descending", 18, 3),
             it("2020-10-13", "ascending", 55, 4)]
    orbit, rel, sel = wh.pick_track(items)
    assert (orbit, rel) == ("descending", 18) and [f["properties"]["datetime"][:10] for f in sel] == ["2020-10-10", "2020-10-22"]


def test_cong_chua_dat_thi_api_tu_choi_bat(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import routes_water
    from app.main import app
    g = tmp_path / "gate.json"
    g.write_text(json.dumps({"passed": False, "run_at": "2026-10-09", "cases": []}), encoding="utf-8")
    monkeypatch.setattr(routes_water, "GATE", str(g))
    with TestClient(app) as c:
        assert c.get("/api/water/status").json()["enabled"] is False
        r = c.post("/api/water/history", json={"lat": 16.575, "lon": 107.495})
    assert r.status_code == 409


def test_ho_so_chi_dua_lich_su_nuoc_da_doc_va_khi_cong_dat(monkeypatch):
    from app import routes_water
    from app.services import cache_store, dossier
    fake = {"available": True, "n_scenes": 300, "first": "2017-01-11", "last": "2026-09-28",
            "track": {"orbit": "descending", "relative_orbit": 18, "collection": "sentinel-1-rtc"}, "n_events": 1,
            "events": [{"start": "2020-10-10", "end": "2020-10-13", "peak_cover": "≥50%", "n_scenes": 2,
                        "min_p50_db": -18.3, "dates": ["2020-10-10", "2020-10-13"]}],
            "method": "m", "limits": "l", "series": [["2020-10-10", -18.3, -19.8]]}
    monkeypatch.setattr(cache_store, "get", lambda key: fake if key.startswith("water:") else None)
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    w = dossier._water_section(16.575, 107.495)
    assert w["n_events"] == 1 and w["events"][0]["peak_cover"] == "≥50%" and "series" not in w and "dates" not in w["events"][0]
    assert dossier.EVIDENCE_CLASSES["water_history_radar"] == "measured"
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": False})
    assert dossier._water_section(16.575, 107.495) is None          # cổng chưa đạt → không vào hồ sơ ký


def test_canh_radar_mot_ngay_cho_thanh_thoi_gian(monkeypatch):
    """GĐ2 — thanh kéo theo năm: chọn đúng quỹ đạo của lịch sử đã đọc, URL ô ảnh có mặt nạ bỏ vùng ngoài dải quét."""
    from fastapi.testclient import TestClient
    from app import routes_water
    from app.main import app
    from app.services import cache_store, mpc, water_history as wh
    feats = [{"id": "S1B_khac_rtc", "properties": {"datetime": "2020-10-13T22:44:00Z", "sat:orbit_state": "descending", "sat:relative_orbit": 18}},
             {"id": "S1A_dung_rtc", "properties": {"datetime": "2020-10-13T10:56:54Z", "sat:orbit_state": "ascending", "sat:relative_orbit": 55}}]
    store: dict = {"water:x": None}
    hist = {"available": True, "track": {"orbit": "ascending", "relative_orbit": 55, "collection": wh.COLLECTION}}
    monkeypatch.setattr(cache_store, "get", lambda key: hist if key.startswith("water:") else store.get(key))
    monkeypatch.setattr(cache_store, "put", lambda key, v, ttl: store.__setitem__(key, v))
    monkeypatch.setattr(mpc, "_call", lambda url, payload=None, timeout=None: {"features": feats})
    s = wh.scene(16.5751, 107.4952, "2020-10-13")
    assert s["item"] == "S1A_dung_rtc" and s["relative_orbit"] == 55
    assert "where%28%28vv%3E0%29%26%28vv%3C0.0158%29%2C1%2C0%29" in s["water_tiles"] and "{z}/{x}/{y}" in s["water_tiles"]
    assert "GỒM CẢ sông" in s["legend"]
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    with TestClient(app) as c:
        assert c.get("/api/water/scene?lat=16.5751&lon=107.4952&date=2020-10-13").json()["item"] == "S1A_dung_rtc"
        assert c.get("/api/water/scene?lat=16.5751&lon=107.4952&date=13-10-2020").status_code == 422
        monkeypatch.setattr(wh, "scene", lambda *a: None)
        assert c.get("/api/water/scene?lat=16.5751&lon=107.4952&date=2020-10-12").status_code == 404
