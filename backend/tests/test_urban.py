"""Ở KHU ĐÔ THỊ, "không ngập" không bao giờ được chấm Khớp (kiểm toàn bộ 17/10/2026).

Đo trên production 17/10/2026, tin "Nhà phố không bao giờ ngập nước" → Khớp ở cả ba điểm giữa phố, vì radar không
thấy ngập giữa nhà cửa (phản xạ kép). Số WorldCover 2021 thật trong khung đo radar (bán kính 100 m), dùng làm giả lập:
    Hoàn Kiếm  21.03, 105.85   Bề mặt xây dựng 86,0%   lịch sử nước 0 đợt / 284 cảnh
    TP Bến Tre 10.24, 106.37   Bề mặt xây dựng 90,1%   0 đợt / 451 cảnh
    TP Cà Mau   9.18, 105.15   Bề mặt xây dựng 92,6%   0 đợt / 440 cảnh
Đối chứng — đồng lúa Quảng Điền, Huế 16.5751, 107.4952: Trồng trọt 99,0%, xây dựng 0,2%, 7 đợt nước → vẫn "mâu thuẫn".
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.do_thi_that

HOAN_KIEM, BEN_TRE, CA_MAU, QUANG_DIEN = (21.03, 105.85), (10.24, 106.37), (9.18, 105.15), (16.5751, 107.4952)
VUON_DUA = (10.30, 106.37)          # vườn dừa Bến Tre — đo 17/10/2026: WorldCover Tán cây 100% trong khung đo
WC = {HOAN_KIEM: {"50": 454, "10": 74}, BEN_TRE: {"50": 436, "10": 48}, CA_MAU: {"50": 448, "80": 32, "10": 4},
      QUANG_DIEN: {"40": 501, "10": 4, "50": 1}, VUON_DUA: {"10": 505}}
HIST = {HOAN_KIEM: (0, 284), BEN_TRE: (0, 451), CA_MAU: (0, 440), QUANG_DIEN: (7, 327), VUON_DUA: (0, 451)}
TIN = "Nhà phố không bao giờ ngập nước"


@pytest.fixture
def fake(monkeypatch):
    from app import routes_water
    from app.services import cache_store, landuse, passport, water_history as wh
    near = lambda la, lo, tbl: next((v for (a, b), v in tbl.items() if abs(a - la) < 1e-3 and abs(b - lo) < 1e-3), None)  # noqa: E731
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo, radius_m=60.0: (
        {"item": "ESA_WorldCover_10m_2021_v200", "hist": h} if (h := near(la, lo, WC)) else None))
    keys = {wh.cache_key(*p): p for p in HIST}
    real_get = cache_store.get

    def get(key):
        if key in keys:
            n, scenes = HIST[keys[key]]
            ev = [{"start": f"20{17 + i}-10-10", "end": f"20{17 + i}-10-12", "n_scenes": 1, "peak_cover": "≥50%", "min_p50_db": -19.0}
                  for i in range(n)]
            return {"available": True, "n_events": n, "events": ev, "n_scenes": scenes, "first": "2017-01-04", "last": "2026-10-10",
                    "baseline_db": {"p10": -11.8, "p25": -10.4, "p50": -8.8, "p75": -7.4}, "series": [], "method": "m", "limits": "l",
                    "track": {"orbit": "descending", "relative_orbit": 18, "collection": "sentinel-1-rtc"}}
        return real_get(key)
    monkeypatch.setattr(cache_store, "get", get)
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    monkeypatch.setattr(passport, "terrain", lambda la, lo: None)


@pytest.mark.parametrize("pt,pct", [(HOAN_KIEM, 86.0), (BEN_TRE, 90.1), (CA_MAU, 92.6)])
def test_khong_ngap_o_pho_la_khong_du_du_lieu(fake, pt, pct):
    from app.services import listing_check as lc
    r = lc.check(TIN, *pt)
    c = next(c for c in r["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "insufficient", c
    assert "Khu đô thị" in c["evidence"] and f"{pct:g}%" in c["evidence"] and "KHÔNG có nghĩa là không ngập" in c["evidence"]


def test_cao_rao_o_pho_cung_khong_duoc_cham_khop(fake):
    from app.services import listing_check as lc
    r = lc.check("Nhà cao ráo, không lo ngập", *HOAN_KIEM)
    assert {c["type"]: c["verdict"] for c in r["claims"]} == {"high_ground": "insufficient", "no_flood": "insufficient"}


def test_dong_lua_quang_dien_van_mau_thuan(fake):
    from app.services import listing_check as lc
    r = lc.check(TIN, *QUANG_DIEN)
    c = next(c for c in r["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "contradicted" and "7 đợt" in c["evidence"]


def test_lich_su_nuoc_va_ho_so_ky_ghi_ro_khu_do_thi(fake):
    from app.services import dossier, narrative, water_history as wh
    u = wh.urban(*HOAN_KIEM)
    assert u["built_pct"] == 86.0 and "KHÔNG nhìn thấy được ngập giữa nhà cửa" in u["note"]
    assert wh.urban(*QUANG_DIEN) is None
    w = dossier._water_section(*HOAN_KIEM)
    assert w["urban"] == {"built_pct": 86.0, "source": "ESA WorldCover 2021"}
    assert "urban" not in dossier._water_section(*QUANG_DIEN)
    text = narrative.template_sentences({"water_history_radar": w}, {"water.summary": {}})[0]["text"]
    assert "khu đô thị" in text and "KHÔNG có nghĩa là không ngập" in text and "chưa thấy nước phủ" not in text


def test_so_sanh_khong_cham_dau_it_dot_nuoc_cho_diem_do_thi(fake, monkeypatch):
    """0 đợt ở giữa phố không được thành giá trị "thuận lợi nhất" của hàng Số đợt nước."""
    from app.services import cache_store, datasources as ds, landuse, listing_check as lc, passport, plot_compare, region
    monkeypatch.setattr(region, "inland_water", lambda la, lo: None)
    monkeypatch.setattr(passport, "history", lambda la, lo: {})
    monkeypatch.setattr(lc, "_nearest_river_km", lambda la, lo, radius_m=3000.0: 1.0)
    monkeypatch.setattr(ds, "distance_to_coast_km", lambda la, lo: 50.0)
    monkeypatch.setattr(ds, "salinity_zone", lambda la, lo: None)
    monkeypatch.setattr(landuse, "composition", lambda la, lo, radius_m=60.0: None)
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds=0: None)
    col = plot_compare.one(*HOAN_KIEM)
    assert isinstance(col["water_events"], str) and "đô thị" in col["water_events"]
    assert plot_compare.one(*QUANG_DIEN)["water_events"] == 7



def test_duoi_tan_cay_day_cung_khong_duoc_cham_khop(fake):
    """Cùng loại sai với đô thị: radar băng C không xuyên tán dày (vườn dừa, rừng, cà phê)."""
    from app.services import dossier, listing_check as lc, narrative, water_history as wh
    c = next(c for c in lc.check(TIN, *VUON_DUA)["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "insufficient" and "Tán cây dày" in c["evidence"] and "100%" in c["evidence"]
    w = dossier._water_section(*VUON_DUA)
    assert w["canopy"]["tree_pct"] == 100.0 and "urban" not in w
    t = narrative.template_sentences({"water_history_radar": w}, {"water.summary": {}})[0]["text"]
    assert "tán cây dày" in t and "chưa thấy nước phủ" not in t
    assert wh.canopy(*QUANG_DIEN) is None and wh.canopy(*HOAN_KIEM) is None


def test_ruong_co_dot_nuoc_kem_loi_nhac_nuoc_tuoi(fake):
    """Đợt nước ở ruộng vẫn là "mâu thuẫn" với "không ngập", nhưng phải nhắc: nước tưới theo vụ cũng hiện thành nước phủ."""
    from app.services import dossier, listing_check as lc
    c = next(c for c in lc.check(TIN, *QUANG_DIEN)["claims"] if c["type"] == "no_flood")
    assert c["verdict"] == "contradicted" and "nước tưới theo vụ" in c["evidence"] and "Tháng các đợt: 10" in c["evidence"]
    assert dossier._water_section(*QUANG_DIEN)["cropland"]["crop_pct"] == 99.0
