"""Lớp diễn giải MÙA LŨ đã bật (cổng đăng ký trước đạt 17/10/2026) — dùng ĐÚNG số trong data/eval/flood_season_result.json:
mưa trung bình tháng ERA5 2016–2025 và ngày bắt đầu các đợt nước của bộ phát hiện GĐ2 (không đổi)."""
from __future__ import annotations

import json
import os

import pytest

pytestmark = [pytest.mark.mua_lu_that, pytest.mark.do_thi_that]

RES = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "eval", "flood_season_result.json"), encoding="utf-8"))
CASES = {(c["lat"], c["lon"]): c for c in RES["cases"]}
QD, CM, HN = (16.5751, 107.4952), (9.18, 105.09), (21.12, 105.89)
WC = {QD: {"40": 501, "10": 4, "50": 1}, CM: {"40": 438, "10": 49, "80": 9, "50": 3, "60": 1}, HN: {"40": 498, "50": 2}}


@pytest.fixture
def fake(monkeypatch):
    from app import routes_water
    from app.services import cache_store, flood_season as fs, landuse, passport, water_history as wh
    near = lambda la, lo, tbl: next((v for (a, b), v in tbl.items() if abs(a - la) < 1e-3 and abs(b - lo) < 1e-3), None)  # noqa: E731
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo, radius_m=60.0: (
        {"item": "ESA_WorldCover_10m_2021_v200", "hist": h} if (h := near(la, lo, WC)) else None))
    monkeypatch.setattr(fs, "season", lambda la, lo: (
        {**fs.season_from_monthly(c["monthly_mm"]), "window": "2016–2025", "source": "ERA5", "rule_v": 1}
        if (c := near(la, lo, CASES)) else None))
    keys = {wh.cache_key(*p): p for p in (QD, CM, HN)}
    real_get = cache_store.get

    def get(key):
        if key in keys:
            c = CASES[keys[key]]
            ev = [{"start": e["start"], "end": e["start"], "n_scenes": 1, "peak_cover": "10–25%", "min_p50_db": -15.0, "dates": [e["start"]]}
                  for e in c["all_events"]]
            return {"available": True, "n_events": len(ev), "events": ev, "n_scenes": 440, "first": "2017-01-04", "last": "2026-10-10",
                    "baseline_db": {"p10": -11.0, "p25": -9.5, "p50": -8.0, "p75": -6.5}, "series": [], "method": "m", "limits": "l",
                    "track": {"orbit": "descending", "relative_orbit": 18, "collection": "sentinel-1-rtc"}}
        return real_get(key)
    monkeypatch.setattr(cache_store, "get", get)
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    monkeypatch.setattr(passport, "terrain", lambda la, lo: None)


def test_cong_da_dat_va_mua_lu_dung_nhu_ket_qua_cong():
    from app.services import flood_season as fs
    assert RES["passed"] is True and fs.gate_passed()
    assert fs.season_from_monthly(CASES[CM]["monthly_mm"])["months"] == [7, 8, 9, 10, 11]
    assert fs.season_from_monthly(CASES[HN]["monthly_mm"])["months"] == [7, 8, 9, 10]
    assert fs.season_from_monthly(CASES[QD]["monthly_mm"])["months"] == [1, 10, 11, 12]


def test_ca_mau_tach_3_dot_trong_mua_10_dot_ngoai_mua(fake):
    from app.services import water_history as wh
    r = wh.history(*CM)
    assert (r["n_in"], r["n_out"]) == (3, 10) and r["flood_season"]["text"] == "7–11"
    assert r["out_note"] == "thường là nước tưới / nuôi trồng theo vụ"          # ruộng 87% → giải thích nước tưới
    assert {e["start"] for e in r["events"] if e["season"] == "in"} == {"2020-08-05", "2021-08-30", "2026-09-16"}


def test_tin_dang_chi_dot_trong_mua_lu_moi_lam_mau_thuan(fake):
    from app.services import listing_check as lc
    c = next(c for c in lc.check("Đất không bao giờ ngập", *CM)["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "contradicted" and "3 đợt TRONG mùa lũ" in c["evidence"] and "Thêm 10 đợt ngoài mùa" in c["evidence"]
    c = next(c for c in lc.check("Đất không bao giờ ngập", *QD)["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "contradicted" and "7 đợt TRONG mùa lũ" in c["evidence"]


def test_chi_co_dot_ngoai_mua_thi_khong_du_du_lieu(fake, monkeypatch):
    """Hà Nội nếu chỉ còn các đợt tháng 2–3 (cấy lúa xuân): "không ngập" KHÔNG bị chấm mâu thuẫn oan."""
    from app.services import listing_check as lc
    monkeypatch.setitem(CASES, HN, {**CASES[HN], "all_events": [e for e in CASES[HN]["all_events"] if e["start"][5:7] in ("02", "03")]})
    c = next(c for c in lc.check("Đất không bao giờ ngập", *HN)["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "insufficient" and "đều NGOÀI mùa lũ" in c["evidence"] and "nước tưới" in c["evidence"]


def test_ho_so_ky_va_loi_dien_giai_ghi_cung_cach_tach(fake):
    from app.services import dossier, narrative
    w = dossier._water_section(*CM)
    assert (w["n_in"], w["n_out"]) == (3, 10) and w["flood_season"]["months"] == [7, 8, 9, 10, 11]
    assert [e["season"] for e in w["events"]].count("out") == 10 and "cropland" not in w
    cat = narrative.catalog({"water_history_radar": w})
    t = narrative.template_sentences({"water_history_radar": w}, cat)[0]["text"]
    assert "3 đợt TRONG mùa lũ (tháng 7–11" in t and "Thêm 10 đợt ngoài mùa lũ" in t and "13 đợt" not in t
    assert "ngoài mùa lũ" in cat["water.event.1"]["value"]                  # 2017-05-29


def test_ho_so_cu_khong_co_lop_mua_lu_giu_nguyen_cau_cu():
    from app.services import narrative
    w = {"n_events": 2, "n_scenes": 300, "first": "2017-01-04", "last": "2026-10-10",
         "events": [{"start": "2020-10-10", "end": "2020-10-12", "peak_cover": "≥50%", "n_scenes": 1}, {"start": "2025-11-01", "end": "2025-11-01", "peak_cover": "≥50%", "n_scenes": 1}]}
    t = narrative.template_sentences({"water_history_radar": w}, {"water.summary": {}})[0]["text"]
    assert t.startswith("Radar Sentinel-1 thấy nước phủ thửa 2 đợt") and "mùa lũ" not in t


def test_v2_truot_nen_khong_bat_giu_nguyen_v1():
    """Cổng v2 (đăng ký 2683146) TRƯỢT 17/10/2026 — Noru không đánh giá được, Cà Mau 05/04/2025 bị bắt nhầm. Giữ v1."""
    from app.services import flood_season as fs
    r2 = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "eval", "flood_season_v2_result.json"), encoding="utf-8"))
    assert r2["passed"] is False and fs.gate_v2_passed() is False and fs.gate_passed() is True
    bad = {c["id"]: c["pass"] for c in r2["cases"]}
    assert bad == {"pos_soulik": True, "pos_noru": False, "neg_camau": False, "neg_hanoi": True, "v1_hue_2020": True, "v1_mientrung_2025": True}


def test_v3_truot_ca_R_a_va_R_b_nen_khong_bat():
    """Cổng v3 (đăng ký 59837ec / A2 e80bd09 / ca 3a812f6) TRƯỢT 17/10/2026: dương tính 0/3, thiếu ca. Giữ v1."""
    from app.services import flood_season as fs
    r3 = fs.gate_v3()
    assert r3 is not None and r3["passed"] is False and r3["enabled_rule"] is None
    for k in ("a", "b"):
        x = r3["rules"][k]
        assert (x["caught"], x["n_pos"], x["false_positives"], x["v1_pass"]) == (0, 3, 0, True)
